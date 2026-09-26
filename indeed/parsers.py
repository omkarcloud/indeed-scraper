"""Raw Indeed payloads -> clean API objects. Pure functions, no network;
every parser tolerates missing / null / wrong-typed fields and never raises
on a partial payload.

Jobs come from the app GraphQL (job(), facets()); everything company-side
comes from the web pages' SSR JSON (company_*(), career_salaries(),
company_search()); autocomplete() shapes autocomplete.indeed.com answers.

Intentionally dropped everywhere: tracking keys, csrf / session tokens (tk,
ctk, hashedCsrfToken), logging and A/B-test blobs (reactProctor), DSA
report links, presentation strings (aria labels, h2 headers, formatted
duplicates of numbers we return, brand colours), the Indeed Apply token (a
base64 blob with an API token; reduced to is_easy_apply), and duplicated
data (recruit.viewJobUrl == url; the per-size logo variants).
"""
import re

from indeed import refdata
from indeed import shared as S


def g(obj, *path, default=None):
    """Safe nested get: g(d, "a", "b", 0) -> d["a"]["b"][0] or default."""
    for step in path:
        if isinstance(step, int):
            if not isinstance(obj, list) or not -len(obj) <= step < len(obj):
                return default
            obj = obj[step]
        else:
            if not isinstance(obj, dict):
                return default
            obj = obj.get(step)
        if obj is None:
            return default
    return obj


def as_list(value):
    return value if isinstance(value, list) else []


def as_dict(value):
    return value if isinstance(value, dict) else {}


# ---- job attributes -------------------------------------------------------------------------

_EDUCATION_RE = re.compile(r"\b(degree|diploma|ged|bachelor|master|doctor|associate'?s|mba|high school|ph\.?d|"
                           r"graduate|postgraduate)\b", re.I)
_SCHEDULE_RE = re.compile(r"\bshifts?\b|weekend|monday to friday|\bon call\b|^overtime$|^holidays$|\b\d+x\d+\b|"
                          r"\b\d+[- ]hour\b|days? per week|\bnight\b|overnight|evening|rotating|^on demand$|"
                          r"^home time$|flexible (work )?hours|^no weekends$", re.I)
_BENEFIT_RE = re.compile(r"insurance|401\(?k\)?|403\(?b\)?|pension|retirement|paid time off|\bpto\b|paid .*leave|"
                         r"parental leave|maternity|paternity|stock|\brsus?\b|equity|bonus|reimbursement|discount|"
                         r"employee assistance|tuition|relocation|parking|wellness|\bgym\b|commuter|flexible spending|"
                         r"health savings|child ?care|referral program|profit sharing|loan|\bmeals?\b|food provided|"
                         r"company car|work from home|flexible schedule|sick time|vacation|paid holidays|"
                         r"professional development|uniform|housing|transportation|visa sponsorship|"
                         r"adoption|fertility|pet insurance|travel", re.I)
_EXPERIENCE_RE = re.compile(r"^(under |less than |at least )?\d+(\.\d+)?\+? (years?|months?)$", re.I)
_PAY_RE = re.compile(r"^(hourly|daily|weekly|bi-?weekly|monthly|commission) pay$|^tips$|^per diem$|^piece rate$", re.I)


def split_attributes(attributes):
    """Indeed's flat job attribute list -> readable groups. Known ids (the
    site's own filter groups) win; the rest is grouped by label; anything
    unrecognised is a skill / requirement."""
    out = {"job_types": [], "work_setting": None, "experience_level": None, "education": [],
           "experience_required": [], "schedules": [], "benefits": [], "pay_types": [], "skills": []}
    for item in as_list(attributes):
        key = S.text(g(item, "key"))
        label = S.text(g(item, "label"))
        if not label or label == key:
            continue
        if key in refdata.JOB_TYPE_IDS:
            out["job_types"].append(label)
        elif key in refdata.WORK_SETTING_IDS:
            # remote wins over hybrid when a job carries both tags
            if out["work_setting"] != "remote":
                out["work_setting"] = refdata.WORK_SETTING_IDS[key]
        elif key in refdata.EXPERIENCE_LEVEL_IDS:
            out["experience_level"] = out["experience_level"] or refdata.EXPERIENCE_LEVEL_IDS[key]
        elif key in refdata.SCHEDULE_IDS:
            out["schedules"].append(label)
        elif key in refdata.BENEFIT_IDS:
            out["benefits"].append(label)
        elif key in refdata.PAY_TYPE_IDS or _PAY_RE.search(label):
            out["pay_types"].append(label)
        elif _EXPERIENCE_RE.match(label):
            out["experience_required"].append(label)
        elif _EDUCATION_RE.search(label):
            out["education"].append(label)
        elif _SCHEDULE_RE.search(label):
            out["schedules"].append(label)
        elif _BENEFIT_RE.search(label):
            out["benefits"].append(label)
        else:
            out["skills"].append(label)
    return out


# ---- jobs (GraphQL) ----------------------------------------------------------------------------

def salary(compensation):
    """compensation {baseSalary | estimated} -> {min, max, currency, period, text, is_estimated}."""
    comp = as_dict(compensation)
    base = as_dict(comp.get("baseSalary"))
    estimated = as_dict(comp.get("estimated"))
    source = base if base.get("range") or base.get("unitOfWork") else as_dict(estimated.get("baseSalary"))
    rng = as_dict(source.get("range"))
    low, high = S.amount(rng.get("min")), S.amount(rng.get("max"))
    text = S.text(comp.get("formattedText")) or S.text(estimated.get("formattedText"))
    if low is None and high is None and not text:
        return None
    return {
        "min": low,
        "max": high,
        "currency": S.text(comp.get("currencyCode")) or S.text(estimated.get("currencyCode")),
        "period": S.period(source.get("unitOfWork")),
        "text": text,
        "is_estimated": not bool(base.get("range") or base.get("unitOfWork")),
    }


def job_location(loc):
    loc = as_dict(loc)
    formatted = as_dict(loc.get("formatted"))
    out = {
        "display_name": S.text(formatted.get("long")) or S.text(formatted.get("short")),
        "address": S.text(loc.get("streetAddress")),
        "neighborhood": S.text(loc.get("neighborhood")),
        "city": S.text(loc.get("city")),
        "postal_code": S.text(loc.get("postalCode")),
        "state": S.text(loc.get("admin1Name")),
        "state_code": S.text(loc.get("admin1Code")),
        "country": S.text(loc.get("countryName")),
        "country_code": S.text(loc.get("countryCode")),
        "latitude": S.num(loc.get("latitude")),
        "longitude": S.num(loc.get("longitude")),
    }
    return out if any(v is not None for v in out.values()) else None


def _rating_value(node):
    return S.rating(g(node, "value"))


def employer_ratings(ugc_stats):
    ratings = as_dict(g(ugc_stats, "ratings"))
    out = {
        "work_life_balance": _rating_value(ratings.get("workLifeBalanceRating")),
        "pay_and_benefits": _rating_value(ratings.get("compensationAndBenefitsRating")),
        "job_security_and_advancement": _rating_value(ratings.get("jobSecurityAndAdvancementRating")),
        "management": _rating_value(ratings.get("managementRating")),
        "culture": _rating_value(ratings.get("cultureAndValuesRating")),
    }
    return out if any(v is not None for v in out.values()) else None


def employer(raw, country, full=False):
    """A GraphQL Employer -> company object (compact for search results,
    with the full dossier for job details / company profiles)."""
    emp = as_dict(raw)
    if not emp.get("name") and not emp.get("key"):
        return None
    slug = S.company_slug(emp.get("relativeCompanyPageUrl"))
    dossier = as_dict(emp.get("dossier"))
    images = as_dict(dossier.get("images"))
    overall = as_dict(g(emp, "ugcStats", "ratings", "overallRating"))
    out = {
        "id": S.text(emp.get("key")),
        "name": S.text(emp.get("name")),
        "slug": slug,
        "link": S.company_link(country, slug),
        "logo": S.text(images.get("squareLogoUrl")),
        "rating": S.rating(overall.get("value")),
        "review_count": S.to_int(overall.get("count")),
    }
    if not full:
        return out
    details = as_dict(dossier.get("employerDetails"))
    links = as_dict(dossier.get("links"))
    ceo_name = S.text(details.get("ceoName"))
    out.update({
        "description": S.multiline(details.get("briefDescription")),
        "industry": S.code_label(details.get("industry")),
        "employee_count": S.text(details.get("employeesLocalizedLabel")),
        "revenue": S.text(details.get("revenueLocalizedLabel")),
        "addresses": [a for a in (S.text(x) for x in as_list(details.get("addresses"))) if a],
        "website": S.text(links.get("corporateWebsite")),
        "social_links": {
            "facebook": S.text(links.get("facebook")),
            "twitter": S.text(links.get("twitter")),
            "instagram": S.text(links.get("instagram")),
        },
        "ceo": {"name": ceo_name, "photo": S.text(details.get("ceoPhotoUrl"))} if ceo_name else None,
        "ratings": employer_ratings(emp.get("ugcStats")),
        "header_image": S.text(images.get("headerImageUrl")),
        "banner_logo": S.text(images.get("rectangularLogoUrl")),
    })
    return out


def job(raw, country="US", full=False):
    """A GraphQL Job -> job object. `full` adds the HTML description and the
    employer profile (job details); search results carry the plain-text
    description and a compact company."""
    j = as_dict(raw)
    key = S.text(j.get("key"))
    loc = job_location(j.get("location"))
    job_country = (loc or {}).get("country_code") or country
    groups = split_attributes(j.get("attributes"))
    recruit = as_dict(j.get("recruit"))
    description = as_dict(j.get("description"))
    hiring = as_dict(j.get("hiringDemand"))
    out = {
        "id": key,
        "title": S.text(j.get("title")),
        "normalized_title": S.text(j.get("displayTitle")),
        "link": S.job_link(job_country, key),
        "apply_link": S.text(j.get("url")) or S.text(recruit.get("viewJobUrl")),
        # the object is present on every job; only an easy-apply job has scopes (DESKTOP / MOBILE)
        "is_easy_apply": bool(as_list(g(j, "indeedApply", "scopes"))),
        "company": employer(j.get("employer"), job_country, full=full),
        "source": S.text(g(j, "source", "name")),
        "location": loc,
        "work_setting": groups["work_setting"],
        "salary": salary(j.get("compensation")),
        "salary_details": S.text(recruit.get("detailedSalary")),
        "job_types": groups["job_types"],
        "experience_level": groups["experience_level"],
        "experience_required": groups["experience_required"],
        "education": groups["education"],
        "schedules": groups["schedules"],
        "work_schedule": S.multiline(recruit.get("workSchedule")),
        "pay_types": groups["pay_types"],
        "benefits": groups["benefits"],
        "skills": groups["skills"],
        "occupations": [o for o in (S.text(g(x, "label")) for x in as_list(j.get("occupations"))) if o],
        "description": S.multiline(description.get("text")),
    }
    if full:
        out["description_html"] = description.get("html") or None
    out.update({
        "is_urgently_hiring": bool(hiring.get("isUrgentHire")),
        "is_high_volume_hiring": bool(hiring.get("isHighVolumeHiring")),
        "is_repost": j.get("isRepost") if isinstance(j.get("isRepost"), bool) else None,
        "is_expired": bool(j.get("expired")),
        "date_published": S.local_date_ms(j.get("datePublished")),
        "date_on_indeed": S.iso_datetime_ms(j.get("dateOnIndeed")),
        "expiration_date": S.local_date_ms(j.get("expirationDate")) if S.num(j.get("expirationDate"))
        else S.iso_date(j.get("expirationDate")),
        "language": S.text(j.get("language")),
    })
    return out


def facet_items(items, with_group=False):
    rows = []
    for item in as_list(items):
        key = S.text(g(item, "key"))
        label = S.text(g(item, "label"))
        if not key:
            continue
        row = {"id": key, "name": label if label != key else None, "count": S.to_int(g(item, "count"))}
        if with_group:
            row["group"] = attribute_group(key, label)
        rows.append(row)
    return rows


def attribute_group(key, label):
    """Which job-object list an attribute id lands in (see split_attributes)."""
    groups = split_attributes([{"key": key, "label": label or key}])
    for name, value in groups.items():
        if value:
            return name
    return "skills"


def facets(raw):
    """jobSearch facets -> counts by posting date, attribute, occupation, city."""
    f = as_dict(raw)
    dates = {S.text(g(x, "label")): S.to_int(g(x, "count")) for x in as_list(f.get("dateOnIndeed"))}
    total = dates.pop("all", None)
    return {
        "total_count": total,
        "date_posted": dates,
        "attributes": facet_items(f.get("attributes"), with_group=True),
        "occupations": facet_items(f.get("occupations")),
        "cities": [{
            "name": S.text(g(c, "city")),
            "state_code": S.text(g(c, "admin1Code")),
            "count": S.to_int(g(c, "count")),
        } for c in as_list(g(f, "location", "city")) if g(c, "city")],
    }


# ---- company pages (web SSR) -------------------------------------------------------------------

def company_ref(data, country, slug=None):
    """{id, name, slug, link} from any company page's comp-initialData."""
    d = as_dict(data)
    header = as_dict(d.get("companyPageHeader"))
    slug = slug or S.company_slug(d.get("baseUrl")) or S.company_slug(g(header, "companyHeader", "reviewsUrl"))
    key = (S.text(g(header, "followButton", "encodedFccId")) or S.text(d.get("encodedFccId"))
           or S.text(g(d, "companyPageFooter", "encodedFccId")))
    name = S.text(d.get("companyName")) or S.text(g(header, "companyHeader", "name"))
    return {"id": key, "name": name, "slug": slug, "link": S.company_link(country, slug)}


def _review_categories(cats):
    cats = as_dict(cats)
    out = {
        "work_life_balance": S.rating(cats.get("workLifeBalance")),
        "pay_and_benefits": S.rating(cats.get("compensationBenefits")),
        "job_security_and_advancement": S.rating(cats.get("jobSecurityAdvancement")),
        "management": S.rating(cats.get("management")),
        "culture": S.rating(cats.get("culture")),
    }
    return out if any(v is not None for v in out.values()) else None


def _salary_row(row, country, currency):
    reports = S.to_int(row.get("reportedSalaryCount") or row.get("count"))
    return {
        "job_title": S.text(row.get("title") or row.get("jobTitle")),
        "salary": S.money(row.get("salary") or row.get("formattedMedian")),
        "currency": currency,
        "period": S.period(row.get("salaryType") or row.get("salaryPeriod")),
        "report_count": reports or None,
        "link": S.link(country, row.get("url")),
    }


def _similar_companies(cards, country):
    out = []
    for c in as_list(cards):
        slug = S.company_slug(c.get("companyUrl") or c.get("snapshotLink"))
        out.append({
            "id": S.text(c.get("employerKey")),
            "name": S.text(c.get("companyName")),
            "slug": slug,
            "link": S.company_link(country, slug),
            "logo": S.text(c.get("companyLogoUrl2x")) or S.text(c.get("companyLogoUrl") or c.get("logoUrl")),
            "rating": S.rating(c.get("rating")),
            "review_count": S.to_int(c.get("reviewCount")),
            "salary_count": S.to_int(c.get("salaryCount")),
            "sectors": [s for s in (S.text(x) for x in as_list(c.get("sectors"))) if s],
        })
    return out


def _question(q, country, base_slug=None):
    q = as_dict(q)
    answer = as_dict(q.get("topAnswer"))
    base = S.text(q.get("baseUrl")) or (f"/cmp/{base_slug}" if base_slug else None)
    rel = S.text(q.get("questionUrl"))
    link = S.link(country, f"{base}/{rel}") if base and rel else None
    top = None
    if answer:
        top = {
            "id": S.text(answer.get("answerUid")),
            "text": S.multiline(answer.get("answerText")),
            "date": S.iso_minute(answer.get("creationDate")),
            "author_job_title": S.text(answer.get("jobTitle")),
            "author_location": S.text(answer.get("location")),
            "is_current_employee": answer.get("currentlyEmployed") if isinstance(answer.get("currentlyEmployed"), bool) else None,
            "is_official": bool(answer.get("official")),
        }
    return {
        "id": S.text(q.get("questionUid")),
        "question": S.multiline(q.get("questionText")),
        "date": S.iso_minute(q.get("creationDate")),
        "answer_count": S.to_int(q.get("totalAnswerCount")),
        "link": link,
        "top_answer": top,
    }


def _happiness(module):
    m = as_dict(module)
    if not m.get("compositeScore") and not m.get("individualRatings"):
        return None
    statements = {S.text(s.get("category")): S.text(s.get("surveyStatement")) for s in as_list(m.get("surveyStatements"))}
    return {
        "score": S.to_int(m.get("compositeScore")),
        "response_count": S.to_int(m.get("numberOfResponses")),
        "categories": [{
            "name": S.text(r.get("category")),
            "score": S.to_int(r.get("score")),
            "grade": S.lower_snake(r.get("grade")),
            "description": S.text(r.get("caption")),
            "survey_statement": statements.get(S.text(r.get("category"))),
        } for r in as_list(m.get("individualRatings"))],
    }


def company_details(data, country, slug=None, profile=None):
    """/cmp/<slug> overview (+ the GraphQL employer profile when available)."""
    d = as_dict(data)
    ref = company_ref(d, country, slug)
    header = as_dict(d.get("companyPageHeader"))
    top = as_dict(header.get("companyHeader"))
    about = as_dict(g(d, "aboutSectionViewModel", "aboutCompany"))
    ceo = as_dict(g(d, "aboutSectionViewModel", "aboutCeo"))
    profile = as_dict(profile)
    currency = S.currency_for(country)
    jobs = as_dict(d.get("jobsSectionViewModel"))
    qna = as_dict(d.get("qnaSectionViewModel"))
    employees = S.size_range(about.get("employeeRange"))
    revenue = S.size_range(about.get("revenue"))
    ceo_name = S.text(ceo.get("name")) or g(profile, "ceo", "name")
    out = {
        **ref,
        "logo": S.text(header.get("logoUrl2x")) or S.text(header.get("logoUrl")) or profile.get("logo"),
        "header_image": profile.get("header_image"),
        "description": S.multiline(about.get("description")) or profile.get("description"),
        "industry": S.text(about.get("industry")) or profile.get("industry"),
        "sectors": [s for s in (S.text(x) for x in as_list(about.get("sectorNames"))) if s],
        "founded_year": S.to_int(about.get("founded")),
        "headquarters": S.text(g(about, "headquartersLocation", "address")),
        "addresses": profile.get("addresses") or [],
        "employee_count": {
            "range": profile.get("employee_count"),
            "min": (employees or {}).get("min"),
            "max": (employees or {}).get("max"),
        } if employees or profile.get("employee_count") else None,
        "revenue": {
            "range": profile.get("revenue"),
            "min": (revenue or {}).get("min"),
            "max": (revenue or {}).get("max"),
            "currency": "USD" if revenue else None,
        } if revenue or profile.get("revenue") else None,
        "website": S.text(g(about, "websiteUrl", "url")) or profile.get("website"),
        "social_links": profile.get("social_links"),
        "header_video": S.text(header.get("headerVideoUrl")),
        "ceo": {
            "name": ceo_name,
            "photo": S.text(ceo.get("photoUrl")) or g(profile, "ceo", "photo"),
            "approval_percent": S.to_int(about.get("ceoApproval")),
        } if ceo_name or about.get("ceoApproval") else None,
        "rating": S.rating(top.get("rating")),
        "review_count": S.to_int(top.get("reviewCount")),
        "ratings": _review_categories(g(d, "reviewRatingOverallSectionViewModel", "reviewCategories")),
        "rating_history": [{"year": S.to_int(r.get("year")), "rating": S.rating(r.get("rating"))}
                           for r in as_list(g(d, "reviewRatingOverallSectionViewModel", "overallRating", "ratings"))
                           if r.get("year")],
        "work_happiness": _happiness(d.get("happinessModule")),
        "open_job_count": S.to_int(jobs.get("totalJobCount")),
        "question_count": S.to_int(qna.get("questionCount")),
        "is_profile_claimed": bool(g(header, "claimedProfileSectionWidgetViewModel", "profileClaimed")),
        "top_salaries": [{
            "category": S.text(c.get("categoryTitle")),
            "salaries": [_salary_row(as_dict(s), country, currency) for s in as_list(c.get("salaries"))],
        } for c in as_list(g(d, "salarySectionViewModel", "categories"))],
        "job_locations": [{
            "name": S.text(x.get("name")),
            "open_job_count": S.to_int(x.get("jobCount")),
            "link": S.link(country, x.get("canonicalUrl")),
        } for x in as_list(jobs.get("jobLocations"))],
        "popular_job_titles": [{
            "title": S.text(x.get("displayName")),
            "open_job_count": S.to_int(x.get("jobCount")),
            "rating": S.rating(x.get("reviewRating")),
            "link": S.link(country, x.get("url")),
        } for x in as_list(g(d, "jobTitleSectionViewModel", "jobTitles"))],
        "office_locations": [{
            "name": S.text(x.get("name")),
            "rating": S.rating(x.get("reviewRating")),
            "link": S.link(country, x.get("href")),
        } for x in as_list(g(d, "locationsSectionViewModel", "locations"))],
        "recent_reviews": [_review(as_dict(r), country) for r in as_list(g(d, "reviewsSectionViewModel", "reviews"))],
        "popular_questions": [
            {**_question(q, country, ref["slug"]), "category": S.text(cat.get("category"))}
            for cat in as_list(qna.get("categoryQuestions")) for q in as_list(cat.get("questions"))
        ],
        "faqs": [{"question": S.text(f.get("questionText")), "answer": S.multiline(f.get("answerText"))}
                 for f in as_list(g(d, "faqSectionViewModel", "faqs"))],
        "similar_companies": _similar_companies(g(d, "similarCompaniesSectionViewModel", "similarCompanyCards"), country),
    }
    return out


# ---- reviews ------------------------------------------------------------------------------------

_SUB_RATINGS = (("work_life_balance", "workAndLifeBalanceRating"), ("pay_and_benefits", "compensationAndBenefitsRating"),
                ("job_security_and_advancement", "jobSecurityAndAdvancementRating"),
                ("management", "managementRating"), ("culture", "cultureAndValuesRating"))


def _review(r, country):
    r = as_dict(r)
    ratings = {name: S.rating(g(r, key, "rating") if isinstance(r.get(key), dict) else r.get(key))
               for name, key in _SUB_RATINGS}
    link = S.text(r.get("sharingLink")) or S.link(country, r.get("reviewUrl"))
    responses = []
    for c in as_list(r.get("comments")):
        c = as_dict(c)
        body = S.multiline(c.get("text") or c.get("commentText") or c.get("body"))
        if not body:
            continue
        responses.append({
            "text": body,
            "date": S.iso_date(c.get("submissionDate") or c.get("formattedDate") or c.get("date")
                               or c.get("creationDate")),
            "author": S.text(c.get("author") or c.get("authorName") or c.get("jobTitle")),
        })
    return {
        "id": S.text(r.get("encryptedReviewId")),
        "title": S.text(r.get("title")),
        "text": S.multiline(r.get("text")),
        "pros": S.multiline(r.get("pros")),
        "cons": S.multiline(r.get("cons")),
        "rating": S.rating(r.get("overallRating")),
        "ratings": ratings if any(v is not None for v in ratings.values()) else None,
        "job_title": S.text(r.get("jobTitle")),
        "normalized_job_title": S.text(r.get("normJobTitle")),
        "location": S.text(r.get("location")),
        "country_code": S.text(r.get("country")),
        "is_current_employee": r.get("currentEmployee") if isinstance(r.get("currentEmployee"), bool) else None,
        "helpful_count": S.to_int(r.get("helpful")),
        "unhelpful_count": S.to_int(r.get("unhelpful")),
        "employer_responses": responses,
        "date": S.iso_date(r.get("submissionDate")),
        "link": link,
    }


def _page_items(listing, key, page):
    """The page's items, or [] when Indeed answered a different page (it
    silently clamps an out-of-range `start` to its last page)."""
    served = S.to_int(g(listing, "pagination", "currentPage"))
    if page > 1 and served is not None and served != page:
        return []
    return as_list(g(listing, key))


def _pages(pagination, per_page, total):
    """Total pages: from the result count when known, else the page's own
    last-page link."""
    if total is not None and per_page:
        return max(1, -(-total // per_page))
    return S.to_int(g(pagination, "paginationLastLink", "index")) or 1


def company_reviews(data, country, page, slug=None):
    d = as_dict(data)
    ref = company_ref(d, country, slug)
    listing = as_dict(d.get("reviewsList"))
    filters = as_dict(d.get("reviewsFilters"))
    sidebar = as_dict(d.get("sidebarWidgets"))
    stats = as_dict(sidebar.get("companyPageStats"))
    counts = as_dict(filters.get("reviewsCount"))
    per_page = S.to_int(g(listing, "pagination", "numItemsPerPage")) or 20
    found = S.to_int(counts.get("foundReviewCount"))
    histogram = [S.to_int(x) for x in as_list(g(sidebar, "reviewHistogram", "counts"))]
    topic_ids = {v: k for k, v in refdata.REVIEW_TOPICS.items()}
    insights = as_dict(d.get("insightsSection"))
    return {
        "company": ref,
        "rating": S.rating(g(stats, "overallCompanyRating", "rating")),
        "review_count": S.to_int(counts.get("totalReviewCount")) or S.to_int(g(stats, "overallCompanyRating", "totalReviewCount")),
        "ratings": _review_categories(stats.get("reviewCategories")),
        "rating_distribution": {str(i + 1): n for i, n in enumerate(histogram)} if len(histogram) == 5 else None,
        "highlights": {
            "pros": [p for p in (S.text(x) for x in as_list(insights.get("pros"))) if p],
            "cons": [c for c in (S.text(x) for x in as_list(insights.get("cons"))) if c],
        },
        "topics": [{
            "id": topic_ids.get(S.text(t.get("topicId"))) or S.text(t.get("topicId")),
            "name": S.text(t.get("name")),
            "rating": S.rating(t.get("rating")),
            "review_count": S.to_int(t.get("count")),
        } for t in as_list(filters.get("topics"))],
        "top_job_titles": [{"job_title": S.text(x.get("jobTitle")), "review_count": S.to_int(x.get("count"))}
                           for x in as_list(g(sidebar, "reviewsByJobTitleWidget", "jobTitles"))],
        "top_locations": [{
            "location": S.text(x.get("key")),
            "country": S.text(x.get("countryName")),
            "review_count": S.to_int(x.get("count")),
        } for x in sorted(as_list(filters.get("localLocations")) + as_list(filters.get("globalLocations")),
                          key=lambda x: S.to_int(g(x, "count")) or 0, reverse=True)[:25]],
        "last_updated": S.iso_date(d.get("lastUpdatedDate")),
        "reviews": [_review(r, country) for r in _page_items(listing, "items", page)],
        "pagination": {
            "page": page,
            "items_per_page": per_page,
            "total_count": found,
            "total_pages": _pages(listing.get("pagination"), per_page, found),
        },
    }


# ---- salaries -------------------------------------------------------------------------------------

def company_salaries(data, country, slug=None, job_category=None):
    d = as_dict(data)
    currency = S.currency_for(country)
    header = as_dict(d.get("salaryHeader"))
    popular = as_dict(d.get("salaryPopularJobsSection"))
    satisfaction = as_dict(d.get("salarySatisfactionSidebarWidget"))
    yes_ratio = S.num(satisfaction.get("yesRatio"))
    rows = [{
        "job_title": S.text(p.get("jobTitle")),
        "median_salary": S.money(p.get("formattedMedian")),
        "currency": currency,
        "period": S.period(p.get("salaryPeriod")),
        "confidence": S.lower_snake(p.get("salaryConfidenceLevel")),
        "category": None,
        "report_count": None,
        "range": None,
        "link": S.link(country, p.get("url")),
    } for p in as_list(popular.get("popularJobTitles"))]
    if not rows:
        # non-US sites have no popular-jobs block: per-title medians by category
        for cat in as_list(g(d, "paginatedList", "categories")):
            for p in as_list(g(cat, "salaries")):
                hist = as_dict(p.get("histogram"))
                low, high = S.amount(hist.get("minSalary")), S.amount(hist.get("maxSalary"))
                rows.append({
                    "job_title": S.text(p.get("jobTitle")),
                    "median_salary": S.money(p.get("formattedMedian")),
                    "currency": currency,
                    "period": S.period(p.get("salaryPeriod")),
                    "confidence": S.lower_snake(p.get("salaryConfidenceLevel")),
                    "category": S.text(cat.get("name")),
                    "report_count": S.to_int(p.get("count")) or None,
                    "range": {"min": low, "max": high} if low is not None or high is not None else None,
                    "link": S.link(country, p.get("url")),
                })
    return {
        "company": company_ref(d, country, slug),
        "location": S.text(popular.get("locationDisplayName")) or (S.country(country) or {}).get("name"),
        "job_category": {"id": job_category, "name": refdata.SALARY_CATEGORIES.get(job_category)} if job_category else None,
        "salary_count": S.to_int(header.get("totalSalaryCount")),
        "currency": currency,
        "last_updated": S.iso_date(header.get("formattedLastUpdateDate")),
        "satisfaction": {
            "satisfied_share": round(yes_ratio, 4) if yes_ratio is not None else None,
            "response_count": S.to_int(satisfaction.get("totalCount")),
        } if satisfaction else None,
        "salaries": rows,
        "top_salaries_by_category": [{
            "category": S.text(c.get("categoryTitle")),
            "salaries": [_salary_row(as_dict(s), country, currency) for s in as_list(c.get("salaries"))],
        } for c in as_list(g(d, "categorySalarySection", "categories"))],
        "summary": S.text(g(d, "salaryFooter", "footerText")),
    }


def company_title_salaries(data, country, slug=None):
    """/cmp/<slug>/salaries/<Job-Title>: average, national comparison,
    distribution, top-paying cities, related titles."""
    d = as_dict(data)
    currency = S.currency_for(country)
    stats = as_dict(d.get("salaryWithNationalStats"))
    header = as_dict(d.get("titleSalaryHeader"))
    sidebar = as_dict(d.get("titleSalarySidebar"))
    histogram = as_dict(stats.get("histogram"))
    low, high = S.amount(histogram.get("minSalary")), S.amount(histogram.get("maxSalary"))
    # bar heights (the tallest bar is 90), normalised to each bucket's share of salaries
    heights = [S.num(x) or 0.0 for x in as_list(histogram.get("distribution"))]
    buckets = []
    if low is not None and high is not None and sum(heights) > 0:
        step = (high - low) / len(heights)
        for i, h in enumerate(heights):
            buckets.append({"min": S.amount(low + i * step), "max": S.amount(low + (i + 1) * step),
                            "share": round(h / sum(heights), 4)})
    satisfaction = as_dict(sidebar.get("salarySatisfactionSidebarWidget"))
    yes_ratio = S.num(satisfaction.get("yesRatio"))
    related = []
    for r in as_list(g(sidebar, "careerRelatedTitlesWidget", "relatedTitleEntries")):
        info = S.text(r.get("salaryInfo")) or ""
        related.append({
            "job_title": S.text(r.get("title")),
            "average_salary": S.money(info),
            "currency": currency,
            "period": _period_from_text(info),
            "link": S.link(country, r.get("salaryInfoLink")),
        })
    category = as_dict(d.get("category"))
    return {
        "company": company_ref(d, country, slug),
        "job_title": S.text(stats.get("jobTitleDisplayText")),
        "location": S.text(stats.get("locationDisplayText")),
        "average_salary": S.amount(stats.get("averageSalary")),
        "currency": currency,
        "period": S.period(stats.get("salaryPeriod")),
        "most_common_period": S.period(stats.get("mostCommonSalaryPeriod")),
        "national_average_salary": S.amount(stats.get("nationalAverageSalary")),
        "percent_vs_national_average": S.to_int(stats.get("differenceWithNationalAverage")),
        "salary_count": S.to_int(header.get("totalSalaryCount")),
        "last_updated": S.iso_date(header.get("formattedLastUpdateDate")),
        "range": {"min": low, "max": high} if low is not None or high is not None else None,
        "distribution": buckets,
        "satisfaction": {
            "satisfied_share": round(yes_ratio, 4) if yes_ratio is not None else None,
            "response_count": S.to_int(satisfaction.get("totalCount")),
        } if satisfaction else None,
        "top_paying_cities": [{
            "location": S.text(c.get("location")),
            "average_salary": S.money(c.get("formattedSalary")),
            "currency": currency,
            "period": S.period(c.get("period")),
        } for c in as_list(g(sidebar, "topPaidCities", "topPaidCities"))],
        "related_job_titles": related,
        "category": {
            "name": S.text(category.get("name")),
            "salaries": [_salary_row(as_dict(s), country, currency) for s in as_list(category.get("salaries"))],
        } if category else None,
        "summary": S.text(g(d, "footer", "footerText")),
    }


def _period_from_text(value):
    low = (value or "").lower()
    for word, name in (("hour", "hourly"), ("day", "daily"), ("week", "weekly"), ("month", "monthly"), ("year", "yearly")):
        if word in low:
            return name
    return None


# ---- Q&A / locations / search ------------------------------------------------------------------------

def company_questions(data, country, page, slug=None, topic=None):
    d = as_dict(data)
    ref = company_ref(d, country, slug)
    header = as_dict(d.get("qnaHeaderViewModel"))
    listing = as_dict(d.get("qnaPaginatedQuestionsViewModel"))
    per_page = S.to_int(g(listing, "pagination", "numItemsPerPage")) or 10
    total = S.to_int(header.get("totalQuestionCount"))
    return {
        "company": ref,
        "topic": topic,
        "question_count": S.to_int(header.get("companyQuestionCount")),
        "questions": [_question(q, country, ref["slug"]) for q in _page_items(listing, "questions", page)],
        "pagination": {
            "page": page,
            "items_per_page": per_page,
            "total_count": total,
            "total_pages": _pages(listing.get("pagination"), per_page, total),
        },
    }


def company_locations(data, country, slug=None):
    d = as_dict(data)

    def rows(items):
        return [{"name": S.text(x.get("name")), "rating": S.rating(x.get("reviewRating")),
                 "link": S.link(country, x.get("href"))} for x in as_list(items) if x.get("name")]
    return {
        "company": company_ref(d, country, slug),
        "states": rows(g(d, "locationStates", "locations")),
        "cities": rows(g(d, "locationCities", "locations")),
    }


def company_search(data, country):
    d = as_dict(data)
    out = []
    for c in as_list(d.get("searchResults")):
        slug = S.company_slug(c.get("companyUrl"))
        out.append({
            "name": S.text(c.get("name")),
            "slug": slug,
            "link": S.company_link(country, slug),
            "logo": S.text(c.get("logoUrl")),
            "rating": S.rating(c.get("rating")),
            "review_count": S.to_int(c.get("reviewsCount")),
            "sectors": [s for s in (S.text(x) for x in as_list(c.get("sectors"))) if s],
            "description": S.multiline(c.get("highlightMessage")),
            "reviews_link": S.link(country, c.get("reviewsUrl")),
            "salaries_link": S.link(country, c.get("salariesUrl")),
            "jobs_link": S.link(country, c.get("jobsUrl")),
        })
    return {"query": S.text(d.get("what")), "location": S.text(d.get("where")), "companies": out}


# ---- career salaries (Next.js) --------------------------------------------------------------------------

_PERIOD_ORDER = ("HOURLY", "DAILY", "WEEKLY", "MONTHLY", "YEARLY")
_DIMENSIONS = {"SKILL": "skills", "FIELDS_OF_STUDY": "fields_of_study", "CERTIFICATION": "certifications",
               "LICENSE": "licenses", "EDUCATION": "education"}


def _salary_stats(node, sample=None):
    node = as_dict(node)
    if not node:
        return None
    out = {
        "median": S.amount(node.get("estimatedMedian")),
        "min": S.amount(node.get("estimatedMin")),
        "max": S.amount(node.get("estimatedMax")),
        "mean": S.amount(node.get("mean")),
        "sample_count": S.to_int(sample if sample is not None else node.get("numDataPoints")),
        "last_updated": S.iso_datetime_ms(node.get("lastUpdateTimestamp")),
    }
    return out if any(out[k] is not None for k in ("median", "mean", "min", "max")) else None


def _salary_block(block):
    """A {currency, salaries{PERIOD: stats}, aggregatedSalaries, mostCommonSalaryPeriod} node."""
    block = as_dict(block)
    estimates = as_dict(block.get("salaries"))
    samples = as_dict(block.get("aggregatedSalaries"))
    common = S.text(block.get("mostCommonSalaryPeriod")) or S.text(g(block, "mostCommonSalary", "salaryType"))
    by_period = {}
    for p in _PERIOD_ORDER:
        stats = _salary_stats(estimates.get(p), g(samples, p, "numDataPoints"))
        if stats:
            by_period[S.period(p)] = stats
    return {
        "currency": S.text(block.get("currency")),
        "most_common_period": S.period(common),
        "by_period": by_period,
    }


def _location_info(info):
    details = as_dict(g(info, "locationDetails"))
    if not details and not g(info, "displayLocation"):
        return None
    return {
        "name": S.text(g(info, "displayLocation")) or S.text(details.get("name")),
        "type": S.lower_snake(details.get("type")),
        "code": S.text(details.get("code")),
        "latitude": S.num(details.get("latitude")),
        "longitude": S.num(details.get("longitude")),
    }


def _impact_rows(dimension_groups, limit=25):
    rows = []
    for group in as_list(dimension_groups):
        for item in as_list(g(group, "l2AttributeInfoList")):
            name = S.text(item.get("l2CategoryDisplayName"))
            if not name:
                continue
            rows.append({
                "name": name,
                "category": S.text(item.get("l1CategoryDisplayName")),
                "salary_impact": S.rounded(item.get("avgSalaryImpact"), 4),
                "open_job_count": S.to_int(item.get("numJobOpenings")),
                "company_count": S.to_int(item.get("numCompanies")),
            })
    rows.sort(key=lambda r: r["salary_impact"] if r["salary_impact"] is not None else -1, reverse=True)
    return rows[:limit]


def career_salaries(props, country, title_slug=None):
    p = as_dict(props)
    title = as_dict(p.get("titleInfo"))
    local = as_dict(p.get("localSalaryAggregate"))
    national = as_dict(p.get("nationalSalaryAggregate"))
    local_salary = _salary_block(local.get("salaries"))
    currency = local_salary["currency"] or S.currency_for(country)
    location = _location_info(p.get("locationInfo"))
    is_national = (location or {}).get("type") == "country"
    dims = as_dict(g(local, "salDimensionAttributeInfo", "dimensionsInfoMap"))
    state_map = as_dict(g(local, "salaryMapInfo", "salaryInfoMap")) or as_dict(g(national, "salaryMapInfo", "salaryInfoMap"))
    cities = []
    for c in as_list(g(p, "topPaidCities", "cities")):
        block = _salary_block(g(c, "salary"))
        period = block["most_common_period"]
        stats = block["by_period"].get(period) or {}
        segment = S.text(g(c, "location", "locationUrlSegment"))
        cities.append({
            "location": S.text(g(c, "location", "displayName")),
            "median_salary": stats.get("median"),
            "average_salary": stats.get("mean"),
            "currency": block["currency"] or currency,
            "period": period,
            "sample_count": stats.get("sample_count"),
            "link": S.link(country, f"/career/{title_slug}/salaries/{segment}") if segment and title_slug else None,
        })
    companies = []
    for c in as_list(p.get("topPayingCompanies")):
        main = as_dict(g(c, "salary", "main"))
        slug = S.company_slug(c.get("companyPageUrl"))
        companies.append({
            "id": S.text(c.get("employerKey")),
            "name": S.text(c.get("name")),
            "slug": slug,
            "link": S.company_link(country, slug),
            "rating": S.rating(c.get("rating")),
            "review_count": S.to_int(c.get("reviewCount")),
            "average_salary": S.amount(main.get("mean")),
            "currency": currency,
            "period": S.period(main.get("type")),
            "salary_count": S.to_int(main.get("count")),
        })
    out = {
        "job_title": S.text(title.get("displayTitle")),
        "normalized_title": S.text(title.get("normTitle")),
        "location": location,
        "currency": currency,
        "most_common_period": local_salary["most_common_period"],
        "salaries": local_salary["by_period"],
        "national_salaries": None if is_national or not national else _salary_block(national.get("salaries"))["by_period"],
        "typical_tenure_years": S.num(local.get("tenureYears")),
        "extra_compensation": [{
            "type": S.lower_snake(x.get("compensationType")),
            "average": S.amount(x.get("compensationMean")),
            "currency": currency,
            "period": S.period(x.get("salaryType")),
        } for x in as_list(g(local, "salaries", "compensations"))],
        "salary_by_state": sorted([{
            "state_code": S.text(v.get("stateEnumString")) or k,
            "average_yearly_salary": S.amount(v.get("yearlyAvgSalary")),
            "sample_count": S.to_int(v.get("numSamples")),
            "percent_vs_national": S.rounded(v.get("percentChangeFromBase"), 1),
        } for k, v in state_map.items() if isinstance(v, dict)],
            key=lambda r: r["average_yearly_salary"] or 0, reverse=True),
        "top_paying_cities": cities,
        "top_paying_companies": companies,
        "related_job_titles": [{
            "job_title": S.text(r.get("displayTitle")),
            "average_salary": S.amount(r.get("salaryMean")),
            "currency": currency,
            "period": S.period(r.get("salaryType")),
        } for r in as_list(g(p, "relatedTitlesResponse", "relatedTitles"))],
        # skills / fields of study / … that raise pay most (Indeed's own dimensions)
        "top_pay_factors": {_DIMENSIONS.get(k, S.lower_snake(k)): _impact_rows(v)
                            for k, v in dims.items() if _impact_rows(v)},
    }
    return out


# ---- autocomplete ------------------------------------------------------------------------------------------

def autocomplete(kind, items, country):
    rows = []
    for item in as_list(items):
        if kind == "company":
            item = as_dict(item)
            slug = S.company_slug(item.get("url"))
            name = S.text(item.get("suggestion"))
            if not name:
                continue
            rows.append({
                "id": S.text(item.get("employerKey")),
                "name": name,
                "slug": slug,
                "link": S.company_link(country, slug),
                "logo": S.text(item.get("squareLogo")) or S.text(item.get("squareLogo64")),
            })
        else:
            value = S.text(item if not isinstance(item, dict) else item.get("suggestion"))
            if value:
                rows.append(value)
    return rows
