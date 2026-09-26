"""/indeed/jobs/* — job search, job details, batch lookup and search filters,
all from the Indeed app's GraphQL (fetch.graphql).

Search pages are cut from 100-job upstream chunks: chunk N needs chunk N-1's
cursor, so chunks are memoised in-process (a small LRU) and a customer
walking pages 1..5 costs ONE upstream call. The cursor stops at ~1,000 jobs
per query, hence MAX_PAGES."""
import threading
import time
from collections import OrderedDict

from indeed import cache_config as ttl
from indeed import fetch, gql
from indeed import parsers as P
from indeed import refdata

PER_PAGE = 20
CHUNK = gql.MAX_LIMIT
MAX_PAGES = 50                 # 1,000 jobs: where Indeed's cursor runs out
MAX_BATCH = 20

_chunks = OrderedDict()
_chunks_lock = threading.Lock()
CHUNK_TTL = 900
CHUNK_MAX = 48


def _chunk_memo(key, build):
    now = time.monotonic()
    with _chunks_lock:
        hit = _chunks.get(key)
        if hit and now - hit[0] < CHUNK_TTL:
            _chunks.move_to_end(key)
            return hit[1]
    value = build()
    with _chunks_lock:
        _chunks[key] = (now, value)
        _chunks.move_to_end(key)
        while len(_chunks) > CHUNK_MAX:
            _chunks.popitem(last=False)
    return value


def _radius_unit(radius_unit, country):
    if radius_unit:
        return radius_unit
    return "miles" if country in refdata.MILES_COUNTRIES else "km"


def _chunk(search, country, index):
    """Upstream chunk `index` (100 jobs) -> {jobs, next_cursor, total}."""
    key = (repr(sorted(search.items())), country, index)

    def build():
        cursor = None
        total = None
        if index > 0:
            prev = _chunk(search, country, index - 1)
            cursor, total = prev["next_cursor"], prev["total"]
            if not cursor:
                return {"jobs": [], "next_cursor": None, "total": total, "end": prev["end"]}
        variables = gql.search_variables(limit=CHUNK, cursor=cursor, **search)
        if index == 0:
            variables["intervals"] = [gql.TOTAL_INTERVAL]
        data = fetch.graphql(gql.search_query(with_total=index == 0), variables, country,
                             label=f"job search chunk {index}")
        result = P.as_dict(data.get("jobSearch"))
        if index == 0:
            total = P.facets(result.get("facets"))["total_count"]
        jobs = [P.job(P.g(r, "job"), country) for r in P.as_list(result.get("results")) if P.g(r, "job", "key")]
        return {"jobs": jobs, "next_cursor": P.g(result, "pageInfo", "nextCursor"), "total": total,
                "end": index * CHUNK + len(jobs)}
    return _chunk_memo(key, build)


def _search_params(query, location, radius, radius_unit, sort, country, date_posted, job_type, work_setting,
                   experience_level, education, min_salary, attributes, occupations, employer_id):
    filters = gql.build_filters(date_posted=date_posted, job_type=job_type, work_setting=work_setting,
                                experience_level=experience_level, education=education, attributes=attributes,
                                occupations=occupations, min_salary=min_salary, employer_id=employer_id)
    return {"query": query, "location": location, "radius": radius,
            "radius_unit": _radius_unit(radius_unit, country), "sort": sort, "filters": filters}


def _employer_id(company, country):
    if not company:
        return None
    from indeed import companies
    return companies.employer_id(company, country)


def search(query=None, location=None, country="US", radius=None, radius_unit=None, sort="relevance",
           date_posted=None, job_type=None, work_setting=None, experience_level=None, education=None,
           min_salary=None, company=None, attributes=None, occupations=None, page=1):
    """One page (20 jobs) of an Indeed job search."""
    employer = _employer_id(company, country)
    params = _search_params(query, location, radius, radius_unit, sort, country, date_posted, job_type,
                            work_setting, experience_level, education, min_salary, attributes, occupations,
                            employer)
    offset = (page - 1) * PER_PAGE
    index, start = divmod(offset, CHUNK)
    chunk = _chunk(params, country, index)
    jobs = chunk["jobs"][start:start + PER_PAGE]
    total = _chunk(params, country, 0)["total"]
    reachable = min(total if total is not None else MAX_PAGES * PER_PAGE, MAX_PAGES * PER_PAGE)
    if chunk["next_cursor"] is None:
        # the cursor ran out inside this chunk: never promise pages past it
        reachable = min(reachable, chunk["end"])
    total_pages = -(-reachable // PER_PAGE)
    return {
        "search": {"query": query, "location": location, "country": country, "company_id": employer},
        "jobs": jobs,
        "pagination": {"page": page, "items_per_page": PER_PAGE, "total_count": total,
                       "total_pages": total_pages},
    }


def filters(query=None, location=None, country="US", radius=None, radius_unit=None, date_posted=None,
            job_type=None, work_setting=None, experience_level=None, education=None, min_salary=None,
            company=None, attributes=None, occupations=None):
    """Result counts for a search: by posting date, top 25 attributes (job
    types, levels, benefits, skills …, with the id to filter on), top 25
    occupations and top cities.

    Indeed cannot facet its whole US index (the upstream answers INTERNAL);
    any query, location, company or filter narrows it enough. So a US call
    with nothing to narrow it counts the last 30 days, and says so in
    search.date_posted."""
    employer = _employer_id(company, country)
    if country == "US" and not any((query, location, employer, date_posted, job_type, work_setting,
                                    experience_level, education, min_salary, attributes, occupations)):
        date_posted = "last_30_days"
    params = _search_params(query, location, radius, radius_unit, None, country, date_posted, job_type,
                            work_setting, experience_level, education, min_salary, attributes, occupations,
                            employer)
    params.pop("sort", None)
    variables = gql.search_variables(limit=1, **params)
    variables["intervals"] = gql.DATE_INTERVALS
    variables["top"] = gql.MAX_FACET_TOP
    data = fetch.graphql(gql.facets_query(), variables, country, label="job search filters")
    out = P.facets(P.g(data, "jobSearch", "facets"))
    return {"search": {"query": query, "location": location, "country": country, "company_id": employer,
                       "date_posted": date_posted}, **out}


def _job_data(keys):
    data = fetch.graphql(gql.JOB_DATA_QUERY, {"keys": list(keys)}, "US", label=f"job data ({len(keys)})")
    return [P.g(r, "job") for r in P.as_list(P.g(data, "jobData", "results")) if P.g(r, "job", "key")]


def details(job):
    """One job by key: full description (text + HTML), salary, attribute
    groups, apply link and the employer's profile with ratings."""
    rows = _job_data([job])
    if not rows:
        raise fetch.IndeedNotFound(f"Indeed has no job {job} (expired or removed)")
    return P.job(rows[0], full=True)


def batch(jobs):
    """Up to 20 jobs in one upstream call; unknown keys are listed in not_found."""
    rows = {r.get("key"): r for r in _job_data(jobs)}
    found = [P.job(rows[k], full=True) for k in jobs if k in rows]
    return {"jobs": found, "not_found": [k for k in jobs if k not in rows]}
