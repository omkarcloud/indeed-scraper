"""GraphQL documents for apis.indeed.com and the jobSearch filter builder.

Schema facts (introspection is off; mapped from validation errors 2026-09-26):
  * jobSearch(what, location:{where, radius, radiusUnit: MILES|KILOMETERS},
    limit <= 100, cursor, sort: RELEVANCE|DATE, filters: [JobSearchFilterInput!])
    -> {pageInfo{nextCursor}, results[{trackingKey, job}], facets}. The cursor
    runs out at ~1,000 results per query.
  * A filter object holds ONE type: date {field:"dateOnIndeed", start:"7d"},
    keyword {field, keys} (keys are ANDed), range {field, min, max} (Long) or
    composite {filters:[keyword…]}. A LIST of filters is ANDed. There is no OR.
    keyword fields used: attributes, occupations, indeedEmployerKey.
    range fields used: compensation.baseAnnualSalary.
  * facets: attributes(top<=25) / occupations(top<=25) {key label count},
    location{city{key city admin1Code count}}, dateOnIndeed(intervals:
    [{label, start}]) {label count} — the only source of a total count.
  * Job fields that answer FORBIDDEN for the app key (and null the whole
    payload when asked): description.semanticSegments; snippet needs an
    `indeed-ctk` header; applicants.count is always null; employer reviews /
    salaries (reviewservice) are forbidden.
"""
from indeed import refdata

MAX_LIMIT = 100
MAX_FACET_TOP = 25

_SALARY = "unitOfWork range { ... on Range { min max } }"

JOB_CORE = f"""
    key title displayTitle url language datePublished dateOnIndeed expired expirationDate isRepost
    source {{ name }}
    location {{ city postalCode streetAddress neighborhood countryCode countryName admin1Code admin1Name
               admin2Code latitude longitude formatted {{ short long }} }}
    compensation {{ currencyCode formattedText baseSalary {{ {_SALARY} }}
                   estimated {{ currencyCode formattedText baseSalary {{ {_SALARY} }} }} }}
    attributes {{ key label }}
    occupations {{ key label }}
    hiringDemand {{ isUrgentHire isHighVolumeHiring }}
    indeedApply {{ key scopes }}
    recruit {{ viewJobUrl detailedSalary workSchedule }}
"""

EMPLOYER_RATINGS = """
    ugcStats { ratings {
        overallRating { value count } workLifeBalanceRating { value count }
        compensationAndBenefitsRating { value count } jobSecurityAndAdvancementRating { value count }
        managementRating { value count } cultureAndValuesRating { value count } } }
"""

EMPLOYER_PROFILE = """
    dossier {
        employerDetails { addresses industry employeesLocalizedLabel revenueLocalizedLabel
                          briefDescription ceoName ceoPhotoUrl }
        images { squareLogoUrl headerImageUrl rectangularLogoUrl }
        links { corporateWebsite facebook twitter instagram } }
"""

EMPLOYER_COMPACT = f"""
    employer {{ key name relativeCompanyPageUrl
        dossier {{ images {{ squareLogoUrl }} }}
        ugcStats {{ ratings {{ overallRating {{ value count }} }} }} }}
"""

EMPLOYER_FULL = f"""
    employer {{ key name relativeCompanyPageUrl {EMPLOYER_PROFILE} {EMPLOYER_RATINGS} }}
"""

JOB_SEARCH_FIELDS = JOB_CORE + " description { text } " + EMPLOYER_COMPACT
JOB_DETAIL_FIELDS = JOB_CORE + " description { html text } " + EMPLOYER_FULL

SEARCH_ARGS = ("$what: String, $location: JobSearchLocationInput, $limit: Int, $cursor: String, "
               "$sort: JobSearchSortOrder, $filters: [JobSearchFilterInput!]")
SEARCH_CALL = "jobSearch(what: $what, location: $location, limit: $limit, cursor: $cursor, sort: $sort, filters: $filters)"

# every interval counts jobs posted within it; "all" (100 years) is the total
TOTAL_INTERVAL = {"label": "all", "start": "36500d"}
DATE_INTERVALS = [
    {"label": "last_24_hours", "start": "1d"}, {"label": "last_3_days", "start": "3d"},
    {"label": "last_7_days", "start": "7d"}, {"label": "last_14_days", "start": "14d"},
    {"label": "last_30_days", "start": "30d"}, TOTAL_INTERVAL,
]
DATE_POSTED = {"last_24_hours": "1d", "last_3_days": "3d", "last_7_days": "7d", "last_14_days": "14d",
               "last_30_days": "30d"}


def search_query(with_total):
    """jobSearch returning full job cards (+ the total count on the first chunk)."""
    total = ("facets { dateOnIndeed(intervals: $intervals) { label count } }" if with_total else "")
    args = SEARCH_ARGS + (", $intervals: [JobSearchDateFacetIntervalInput!]!" if with_total else "")
    return f"""query IndeedJobSearch({args}) {{
      {SEARCH_CALL} {{
        pageInfo {{ nextCursor }}
        results {{ job {{ {JOB_SEARCH_FIELDS} }} }}
        {total}
      }}
    }}"""


def facets_query():
    return f"""query IndeedJobFacets({SEARCH_ARGS}, $intervals: [JobSearchDateFacetIntervalInput!]!, $top: Int) {{
      {SEARCH_CALL} {{
        facets {{
          dateOnIndeed(intervals: $intervals) {{ label count }}
          attributes(top: $top) {{ key label count }}
          occupations(top: $top) {{ key label count }}
          location {{ city {{ key city admin1Code count }} }}
        }}
      }}
    }}"""


JOB_DATA_QUERY = f"""query IndeedJobData($keys: [ID!]!) {{
  jobData(jobKeys: $keys) {{ results {{ job {{ {JOB_DETAIL_FIELDS} }} }} }}
}}"""

EMPLOYERS_QUERY = f"""query IndeedEmployers($keys: [ID!]!) {{
  employers(keys: $keys) {{ key name relativeCompanyPageUrl {EMPLOYER_PROFILE} {EMPLOYER_RATINGS} }}
}}"""


def build_filters(date_posted=None, job_type=None, work_setting=None, experience_level=None, education=None,
                  attributes=None, occupations=None, min_salary=None, employer_id=None):
    """Public search params -> the ANDed jobSearch filter list (None = no filter)."""
    filters = []
    if date_posted:
        filters.append({"date": {"field": "dateOnIndeed", "start": DATE_POSTED[date_posted]}})
    keys = []
    for table, value in ((refdata.JOB_TYPES, job_type), (refdata.WORK_SETTINGS, work_setting),
                         (refdata.EXPERIENCE_LEVELS, experience_level), (refdata.EDUCATION_LEVELS, education)):
        if value:
            keys.append(table[value][0])
    for key in attributes or []:
        if key not in keys:
            keys.append(key)
    if keys:
        filters.append({"keyword": {"field": "attributes", "keys": keys}})
    if occupations:
        filters.append({"keyword": {"field": "occupations", "keys": list(occupations)}})
    if min_salary:
        filters.append({"range": {"field": "compensation.baseAnnualSalary", "min": str(int(min_salary))}})
    if employer_id:
        filters.append({"keyword": {"field": "indeedEmployerKey", "keys": [employer_id]}})
    return filters or None


def search_variables(query=None, location=None, radius=None, radius_unit="miles", sort=None, filters=None,
                     limit=MAX_LIMIT, cursor=None):
    variables = {"limit": limit, "sort": "DATE" if sort == "date" else "RELEVANCE"}
    if query:
        variables["what"] = query
    if location:
        variables["location"] = {"where": location, "radius": int(radius if radius is not None else 25),
                                 "radiusUnit": "KILOMETERS" if radius_unit == "km" else "MILES"}
    if cursor:
        variables["cursor"] = cursor
    if filters:
        variables["filters"] = filters
    return variables
