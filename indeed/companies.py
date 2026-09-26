"""/indeed/companies/* — company search, profile, reviews, salaries, Q&A,
office locations (www.indeed.com SSR pages through fetch.comp_data) and
open jobs (GraphQL, filtered by the employer id).

`company` arrives from refs.resolve_company as {"slug", "id"}: a page slug
("Google", "Amazon.com") or an Indeed employer id. Pages need the slug and
GraphQL needs the id, so each is derived from the other when missing (and
cached for a month: neither ever changes)."""
import re
from urllib.parse import quote, unquote_plus

from indeed import cache_config as ttl
from indeed import fetch, gql, jobs
from indeed import parsers as P
from indeed import refdata
from indeed import shared as S

REVIEWS_PER_PAGE = 20
QUESTIONS_PER_PAGE = 10


def _cmp_path(slug, tail=""):
    return f"/cmp/{quote(slug, safe='.,-_&()~')}{tail}"


def slug_of(company, country):
    """The page slug of a resolved `company` (an employer id is looked up
    through GraphQL employers(keys))."""
    if company.get("slug"):
        return company["slug"]
    key = company.get("id")

    def build():
        data = fetch.graphql(gql.EMPLOYERS_QUERY, {"keys": [key]}, country, label=f"employer {key}")
        rows = [r for r in P.as_list(data.get("employers")) if isinstance(r, dict)]
        slug = S.company_slug(P.g(rows, 0, "relativeCompanyPageUrl")) if rows else None
        if not slug:
            raise fetch.IndeedNotFound(f"Indeed has no company with the employer id {key}")
        return slug
    return fetch.shared_raw("employer_slug", {"id": key}, build, ttl.EMPLOYER_ID_CACHE)


def overview_raw(slug, country):
    """The /cmp/<slug> overview comp-initialData (memo + response cache)."""
    return fetch.shared_raw("company_page", {"slug": slug, "country": country},
                            lambda: fetch.comp_data(_cmp_path(slug), country, label=f"company {slug}"),
                            ttl.COMPANY_PAGE_RAW_CACHE)


def employer_id(company, country="US"):
    """The Indeed employer id of a resolved `company` (for GraphQL filters):
    the company autocomplete when it lists the exact page, else the page."""
    if company.get("id"):
        return company["id"]
    slug = company["slug"]

    def build():
        try:
            rows = fetch.autocomplete("company", slug.replace("-", " "), country, count=20)
        except fetch.IndeedUpstreamError:
            rows = []
        for row in P.as_list(rows):
            if (S.company_slug(P.g(row, "url")) or "").lower() == slug.lower() and P.g(row, "employerKey"):
                return row["employerKey"]
        ref = P.company_ref(overview_raw(slug, country), country, slug)
        if not ref.get("id"):
            raise fetch.IndeedNotFound(f"Indeed has no employer id for the company {slug}")
        return ref["id"]
    return fetch.shared_raw("employer_id", {"slug": slug.lower()}, build, ttl.EMPLOYER_ID_CACHE)


# ---- routes -------------------------------------------------------------------------------

def search(query, location=None, country="US"):
    """Companies matching a name (one page of up to ~30 results)."""
    data = fetch.comp_data("/companies/search", country, {"q": query, "l": location},
                           label=f"company search {query!r}")
    return P.company_search(data, country)


def details(company, country="US"):
    """Company profile: overview page + the GraphQL employer profile
    (employee / revenue ranges, social links, header image, addresses)."""
    slug = slug_of(company, country)
    raw = overview_raw(slug, country)
    ref = P.company_ref(raw, country, slug)
    profile = None
    if ref.get("id"):
        try:
            data = fetch.graphql(gql.EMPLOYERS_QUERY, {"keys": [ref["id"]]}, country, label=f"employer {ref['id']}")
            rows = P.as_list(data.get("employers"))
            profile = P.employer(rows[0], country, full=True) if rows else None
        except (fetch.IndeedUpstreamError, fetch.IndeedBadRequest) as e:
            print(f"indeed: employer profile for {slug} skipped: {e}")
    return P.company_details(raw, country, slug, profile)


def reviews(company, country="US", page=1, sort="newest", review_country=None, location=None, job_title=None,
            topic=None, language=None):
    """One page (20) of employee reviews with the rating summary, histogram,
    topic ratings and filter hints."""
    slug = slug_of(company, country)
    params = {
        "start": (page - 1) * REVIEWS_PER_PAGE or None,
        "fcountry": review_country or (country if location else "ALL"),
        "floc": location,
        "fjobtitle": job_title,
        "ftopic": refdata.REVIEW_TOPICS.get(topic) if topic else None,
        "lang": language,
        "sort": refdata.REVIEW_SORTS.get(sort),
    }
    data = fetch.comp_data(_cmp_path(slug, "/reviews"), country, params, label=f"reviews {slug} p{page}")
    return P.company_reviews(data, country, page, slug)


def _salary_location(slug, country, location):
    """'Mountain View, CA' / 'California' / 'CA' -> the page's own location
    filter value (US/CA/Mountain View), read from the salaries page's
    location tree."""
    def build():
        return fetch.comp_data(_cmp_path(slug, "/salaries"), country, label=f"salaries {slug}")
    data = fetch.shared_raw("company_salaries", {"slug": slug, "country": country}, build,
                            ttl.SALARY_FILTERS_RAW_CACHE)
    wanted = " ".join(location.lower().replace(",", " ").split())
    options = []
    stack = list(P.as_list(P.g(data, "salaryFilters", "locations")))
    while stack:
        node = P.as_dict(stack.pop(0))
        stack.extend(P.as_list(node.get("children")))
        name = S.text(node.get("displayText"))
        extra = S.text(node.get("additionalDisplayText"))
        url = S.text(node.get("url")) or ""
        match = re.search(r"[?&]location=([^&]+)", url)
        if not name or not match:
            continue
        label = f"{name}, {extra}" if extra else name
        options.append(label)
        candidates = {name.lower(), label.lower().replace(",", ""), " ".join(label.lower().replace(",", " ").split())}
        if extra:
            candidates.add(extra.lower())
        if wanted in candidates:
            return unquote_plus(match.group(1))
    hint = ", ".join(options[:12])
    raise ValueError(f"Indeed has no salary data for '{location}' at {slug}. Locations with data: {hint}"
                     + (" …" if len(options) > 12 else ""))


def _title_segment(job_title):
    """'software engineer' -> 'Software-Engineer' (the /salaries/<Title> segment)."""
    words = re.split(r"[\s\-]+", job_title.strip())
    return "-".join(w[:1].upper() + w[1:] for w in words if w)


def salaries(company, country="US", job_title=None, location=None, job_category=None):
    """Company salaries: 100 popular job titles with medians and per-category
    tops; with `job_title`, that title's average, range, distribution,
    national comparison, top-paying cities and related titles."""
    slug = slug_of(company, country)
    params = {"location": _salary_location(slug, country, location) if location else None}
    if job_title:
        data = fetch.comp_data(_cmp_path(slug, "/salaries/" + quote(_title_segment(job_title), safe="-")),
                               country, params, label=f"salaries {slug} {job_title}")
        if not P.g(data, "salaryWithNationalStats"):
            raise fetch.IndeedNotFound(f"Indeed has no {job_title} salaries at {slug}")
        return P.company_title_salaries(data, country, slug)
    params["job_category"] = job_category
    data = fetch.comp_data(_cmp_path(slug, "/salaries"), country, params, label=f"salaries {slug}")
    return P.company_salaries(data, country, slug, job_category)


def questions(company, country="US", page=1, topic=None):
    """One page (10) of employee Q&A with each question's top answer."""
    slug = slug_of(company, country)
    tail = "/faq" + (f"/{refdata.QUESTION_TOPICS[topic]}" if topic else "")
    params = {"start": (page - 1) * QUESTIONS_PER_PAGE or None}
    data = fetch.comp_data(_cmp_path(slug, tail), country, params, label=f"questions {slug} p{page}")
    return P.company_questions(data, country, page, slug, topic)


def locations(company, country="US"):
    """Office locations (states and cities) with their review ratings."""
    slug = slug_of(company, country)
    data = fetch.comp_data(_cmp_path(slug, "/locations"), country, label=f"locations {slug}")
    return P.company_locations(data, country, slug)


def open_jobs(company, country="US", query=None, location=None, radius=None, radius_unit=None, sort="relevance",
              date_posted=None, job_type=None, work_setting=None, experience_level=None, education=None,
              min_salary=None, page=1):
    """The company's open jobs (GraphQL search filtered by its employer id)."""
    return jobs.search(query=query, location=location, country=country, radius=radius, radius_unit=radius_unit,
                       sort=sort, date_posted=date_posted, job_type=job_type, work_setting=work_setting,
                       experience_level=experience_level, education=education, min_salary=min_salary,
                       company=company, page=page)
