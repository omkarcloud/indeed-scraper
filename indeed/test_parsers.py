"""Offline tests: refs resolvers, marshmallow schemas, value helpers, parsers
and the endpoint functions with the transport monkeypatched to serve
fixtures (indeed/fixtures/*.json.gz, raw payloads captured 2026-09-26) — no
network.

    python -m pytest indeed/test_parsers.py -q
"""
import gzip
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from indeed import (companies, fetch, gql, jobs, parsers as P, refs, salaries,  # noqa: E402
                    schemas, search, shared as S)
from schema_fields import load_query  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fx(name):
    with gzip.open(os.path.join(FX, name + ".json.gz"), "rt", encoding="utf-8") as f:
        return json.load(f)


# ---- refs ------------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("US", "US"), ("us", "US"), ("United States", "US"), ("uk", "GB"), ("GB", "GB"), ("Germany", "DE"),
    ("uk.indeed.com", "GB"), ("https://de.indeed.com/jobs?q=x", "DE"), ("https://www.indeed.com/cmp/Google", "US"),
])
def test_resolve_country(value, expected):
    assert refs.resolve_country(value) == expected


@pytest.mark.parametrize("value", ["", "ZZ", "Atlantis", "https://example.com/x", "AQ"])
def test_resolve_country_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_country(value)


@pytest.mark.parametrize("value", [
    "bca244a4074f26cb", "BCA244A4074F26CB", "https://www.indeed.com/viewjob?jk=bca244a4074f26cb&from=serp",
    "https://www.indeed.com/jobs?q=python&vjk=bca244a4074f26cb", "https://uk.indeed.com/rc/clk?jk=bca244a4074f26cb&x=1",
    "www.indeed.com/m/viewjob?jk=bca244a4074f26cb", "https://www.indeed.com/cmp/_/job?jk=bca244a4074f26cb",
])
def test_resolve_job(value):
    assert refs.resolve_job(value) == "bca244a4074f26cb"


@pytest.mark.parametrize("value", ["", "hello", "bca244a4074f26c", "https://www.indeed.com/jobs?q=python",
                                   "https://example.com/viewjob?jk=bca244a4074f26cb"])
def test_resolve_job_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_job(value)


@pytest.mark.parametrize("value,expected", [
    ("Google", {"slug": "Google", "id": None}),
    ("Amazon.com", {"slug": "Amazon.com", "id": None}),
    ("Bank of America", {"slug": "Bank-of-America", "id": None}),
    ("https://www.indeed.com/cmp/Google/reviews?fcountry=ALL", {"slug": "Google", "id": None}),
    ("uk.indeed.com/cmp/Tesco", {"slug": "Tesco", "id": None}),
    ("d5cd619626c9f6f7", {"slug": None, "id": "d5cd619626c9f6f7"}),
])
def test_resolve_company(value, expected):
    assert refs.resolve_company(value) == expected


@pytest.mark.parametrize("value", ["", "https://www.indeed.com/viewjob?jk=bca244a4074f26cb", "a/b", "x?y"])
def test_resolve_company_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_company(value)


def test_resolve_job_title_and_location():
    assert refs.resolve_job_title("Software Engineer") == "software-engineer"
    assert refs.resolve_job_title("https://www.indeed.com/career/registered-nurse/salaries/Houston--TX") == "registered-nurse"
    assert refs.career_location_segment("New York, NY") == "New-York--NY"
    assert refs.career_location_segment("CA") == "CA"
    assert refs.career_location_segment("London") == "London"
    assert refs.career_location_segment("https://www.indeed.com/career/nurse/salaries/San-Jose--CA") == "San-Jose--CA"


# ---- schemas -------------------------------------------------------------------------------------

def test_search_schema_defaults_and_choices():
    data, err = load_query(schemas.JobSearchSchema, {"query": " python ", "country": "uk", "job_type": "Full_Time",
                                                     "attributes": "x62bt, CF3CP", "company": "Google"})
    assert err is None
    assert data["query"] == "python" and data["country"] == "GB" and data["page"] == 1
    assert data["job_type"] == "full_time" and data["attributes"] == ["X62BT", "CF3CP"]
    assert data["company"] == {"slug": "Google", "id": None} and data["sort"] == "relevance"


@pytest.mark.parametrize("params", [
    {"page": "51"}, {"job_type": "weird"}, {"country": "ZZ"}, {"attributes": "bad!"}, {"foo": "bar"},
    {"min_salary": "-5"}, {"radius": "999"},
])
def test_search_schema_rejects(params):
    data, err = load_query(schemas.JobSearchSchema, params)
    assert data is None and err["errors"]


def test_batch_and_review_schemas():
    data, err = load_query(schemas.JobBatchSchema, {"jobs": "bca244a4074f26cb, https://www.indeed.com/viewjob?jk=4322ca654f18afae,bca244a4074f26cb"})
    assert err is None and data["jobs"] == ["bca244a4074f26cb", "4322ca654f18afae"]
    assert load_query(schemas.JobBatchSchema, {"jobs": ",".join(["%016x" % i for i in range(21)])})[1]
    data, err = load_query(schemas.CompanyReviewsSchema, {"company": "Google", "review_country": "all", "sort": "Oldest",
                                                          "topic": "management", "language": "EN"})
    assert err is None and data["review_country"] is None and data["sort"] == "oldest" and data["language"] == "en"
    data, err = load_query(schemas.CompanySalariesSchema, {"company": "Google", "job_category": "Software Development"})
    assert err is None and data["job_category"] == "techsoftware"
    data, err = load_query(schemas.AutocompleteSchema, {"query": "dat", "type": "companies"})
    assert err is None and data["limit"] == 10


# ---- value helpers ---------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("$165,027", 165027), ("€ 52.000", 52000), ("$28.26", 28.26), ("£1,234.50", 1234.5), ("52.000,50 €", 52000.5),
    ("₹6,00,000", 600000), ("12,5", 12.5), ("", None), (None, None), ("n/a", None),
])
def test_money(value, expected):
    assert S.money(value) == expected


def test_size_range_code_label_and_dates():
    assert S.size_range("ERv1_10000_PLUS") == {"min": 10000, "max": None}
    assert S.size_range("RRv1_1M_TO_5M") == {"min": 1_000_000, "max": 5_000_000}
    assert S.size_range("RRv1_LESS_THAN_1M") == {"min": None, "max": 1_000_000}
    assert S.size_range("junk") is None and S.size_range(None) is None
    assert S.code_label("Iv1_EDUCATION_AND_SCHOOLS") == "Education and Schools"
    assert S.code_label("Internet & Web Services") == "Internet & Web Services"
    assert S.iso_date("September 22, 2026") == "2026-09-22" and S.iso_date("22 September 2026") == "2026-09-22"
    assert S.iso_date("3. September 2025") is None
    assert S.iso_minute("2021-11-15T22:54Z") == "2021-11-15T22:54:00Z"
    assert S.local_date_ms(1790312400000) == "2026-09-25"           # local midnight, US Central
    assert S.local_date_ms(1790274600000) == "2026-09-25"           # local midnight, IST
    assert S.iso_datetime_ms(1790394257026) == "2026-09-26T03:44:17Z"
    assert S.period("HOUR") == "hourly" and S.period("YEARLY") == "yearly" and S.period("x") is None


def test_split_attributes():
    groups = P.split_attributes([
        {"key": "CF3CP", "label": "Full-time"}, {"key": "DSQF7", "label": "Remote"}, {"key": "PAXZC", "label": "Hybrid work"},
        {"key": "UB7SC", "label": "Senior level"}, {"key": "EY33Q", "label": "Health insurance"},
        {"key": "ZZZZ1", "label": "Master's degree in nursing"}, {"key": "ZZZZ2", "label": "3 years"},
        {"key": "ZZZZ3", "label": "12 hour shift"}, {"key": "ZZZZ4", "label": "Tuition reimbursement"},
        {"key": "8AD9K", "label": "Hourly pay"}, {"key": "X62BT", "label": "Python"}, {"key": "PM67F", "label": "PM67F"},
    ])
    assert groups["job_types"] == ["Full-time"] and groups["work_setting"] == "remote"
    assert groups["experience_level"] == "senior_level" and groups["education"] == ["Master's degree in nursing"]
    assert groups["experience_required"] == ["3 years"] and groups["schedules"] == ["12 hour shift"]
    assert groups["benefits"] == ["Health insurance", "Tuition reimbursement"] and groups["pay_types"] == ["Hourly pay"]
    assert groups["skills"] == ["Python"]


# ---- job parsers ---------------------------------------------------------------------------------------

def test_search_chunk_jobs():
    data = fx("search_chunk")["jobSearch"]
    parsed = [P.job(r["job"], "US") for r in data["results"]]
    assert len(parsed) == 30 and P.facets(data["facets"])["total_count"] > 1000
    for j in parsed:
        assert len(j["id"]) == 16 and j["title"] and j["link"].startswith("https://www.indeed.com/viewjob?jk=")
        assert j["description"] and "description_html" not in j
        assert j["date_on_indeed"].endswith("Z") and len(j["date_published"]) == 10
        assert isinstance(j["is_easy_apply"], bool) and isinstance(j["skills"], list)
    assert any(j["salary"] and j["salary"]["min"] and j["salary"]["period"] for j in parsed)
    assert any(j["company"] and j["company"]["rating"] for j in parsed)


def test_job_details():
    rows = fx("job_data")["jobData"]["results"]
    job = P.job(rows[0]["job"], full=True)
    assert job["id"] == "4322ca654f18afae" and job["description_html"].startswith("<")
    assert job["location"]["city"] == "Chicago" and job["location"]["latitude"]
    company = job["company"]
    assert company["name"] and company["ratings"] and company["employee_count"] and company["social_links"]
    assert company["industry"] and not company["industry"].startswith("Iv1_")


def test_parsers_survive_empty_payloads():
    assert P.job({})["id"] is None and P.job(None)["skills"] == []
    assert P.salary({}) is None and P.job_location(None) is None and P.employer(None, "US") is None
    assert P.facets(None)["attributes"] == []
    assert P.company_details({}, "US")["similar_companies"] == []
    assert P.company_reviews({}, "US", 1)["reviews"] == []
    assert P.company_salaries({}, "US")["salaries"] == []
    assert P.company_title_salaries({}, "US")["distribution"] == []
    assert P.company_questions({}, "US", 1)["questions"] == []
    assert P.company_locations(None, "US")["cities"] == []
    assert P.company_search({}, "US")["companies"] == []
    assert P.career_salaries({}, "US")["salaries"] == {}
    assert P.autocomplete("company", None, "US") == []


def test_facets():
    out = P.facets(fx("facets")["jobSearch"]["facets"])
    assert out["total_count"] and set(out["date_posted"]) == {"last_24_hours", "last_3_days", "last_7_days",
                                                              "last_14_days", "last_30_days"}
    assert len(out["attributes"]) == 25 and all(a["id"] and a["group"] for a in out["attributes"])
    assert out["occupations"] and out["cities"][0]["name"]


# ---- company parsers --------------------------------------------------------------------------------------

def test_company_details():
    profile = P.employer(fx("employers")["employers"][0], "US", full=True)
    out = P.company_details(fx("company_overview"), "US", "Google", profile)
    assert out["id"] == "d5cd619626c9f6f7" and out["name"] == "Google" and out["link"] == "https://www.indeed.com/cmp/Google"
    assert out["rating"] and out["review_count"] > 1000 and out["ratings"]["culture"]
    assert out["employee_count"]["min"] == 10000 and out["revenue"]["min"] == 10_000_000_000
    assert out["ceo"]["name"] and out["founded_year"] == 1998 and out["work_happiness"]["categories"]
    assert out["similar_companies"][0]["id"] and out["popular_questions"][0]["question"] and out["faqs"]


def test_company_reviews():
    out = P.company_reviews(fx("company_reviews"), "US", 1, "Google")
    assert len(out["reviews"]) == 20 and out["pagination"]["total_pages"] > 100
    assert sum(out["rating_distribution"].values()) == out["review_count"]
    assert {t["id"] for t in out["topics"]} == {"work_life_balance", "pay_and_benefits", "job_security_and_advancement",
                                                "management", "culture"}
    r = out["reviews"][0]
    assert r["id"] and r["text"] and r["rating"] and len(r["date"]) == 10 and r["link"].startswith("https://")
    old = P.company_reviews(fx("company_reviews_old"), "US", 3, "Google")
    assert any(x["pros"] for x in old["reviews"]) and any(x["ratings"] for x in old["reviews"])
    # Indeed clamps an out-of-range start to its last page: never serve that as page N
    assert P.company_reviews(fx("company_reviews"), "US", 999, "Google")["reviews"] == []


def test_company_salaries():
    out = P.company_salaries(fx("company_salaries"), "US", "Google")
    assert out["salary_count"] > 1000 and out["currency"] == "USD" and len(out["salaries"]) == 100
    assert out["salaries"][0]["median_salary"] and out["salaries"][0]["period"] in ("yearly", "hourly")
    assert out["satisfaction"]["satisfied_share"] < 1 and out["top_salaries_by_category"][0]["salaries"][0]["report_count"]
    de = P.company_salaries(fx("company_salaries_de"), "DE", "Siemens")
    assert de["currency"] == "EUR" and de["salaries"] and de["salaries"][0]["category"] and de["location"] == "Germany"
    title = P.company_title_salaries(fx("company_title_salaries"), "US", "Google")
    assert title["job_title"] == "Software Engineer" and title["average_salary"] > title["national_average_salary"]
    assert abs(sum(b["share"] for b in title["distribution"]) - 1) < 0.01 and title["top_paying_cities"]


def test_company_questions_locations_search():
    q = P.company_questions(fx("company_questions"), "US", 1, "Google")
    assert len(q["questions"]) == 10 and q["questions"][0]["link"].startswith("https://www.indeed.com/cmp/Google/faq/")
    assert q["pagination"]["total_pages"] >= 2
    loc = P.company_locations(fx("company_locations"), "US", "Google")
    assert len(loc["states"]) > 10 and len(loc["cities"]) > 50 and loc["cities"][0]["link"]
    found = P.company_search(fx("company_search"), "US")
    assert found["companies"][0]["slug"] and found["companies"][0]["review_count"]


def test_career_salaries_and_autocomplete():
    out = P.career_salaries(fx("career_salaries"), "US", "software-engineer")
    assert out["job_title"] == "Software Engineer" and out["currency"] == "USD" and out["most_common_period"] == "yearly"
    assert out["salaries"]["yearly"]["median"] > 50000 and out["salary_by_state"][0]["state_code"]
    assert out["top_paying_cities"][0]["link"].endswith("/career/software-engineer/salaries/" + "San-Jose--CA")
    assert out["top_paying_companies"] and out["related_job_titles"] and out["top_pay_factors"]["skills"]
    rows = P.autocomplete("company", fx("autocomplete_company"), "US")
    assert rows[0]["id"] and rows[0]["slug"] and rows[0]["link"].startswith("https://www.indeed.com/cmp/")
    assert all(isinstance(x, str) for x in P.autocomplete("what", fx("autocomplete_what"), "US"))


# ---- endpoint functions (transport monkeypatched) ------------------------------------------------------------

@pytest.fixture
def offline(monkeypatch):
    """Serve GraphQL / page / autocomplete calls from fixtures; the response
    cache is bypassed."""
    calls = {"graphql": []}
    chunk = fx("search_chunk")

    def graphql(query, variables=None, country="US", label=""):
        calls["graphql"].append((query, variables, country))
        if "IndeedJobSearch" in query:
            data = json.loads(json.dumps(chunk))
            if not (variables or {}).get("intervals"):
                data["jobSearch"].pop("facets", None)
            if (variables or {}).get("cursor"):
                data["jobSearch"]["pageInfo"]["nextCursor"] = None     # second chunk is the last
            return data
        if "IndeedJobFacets" in query:
            return fx("facets")
        if "IndeedJobData" in query:
            rows = fx("job_data")["jobData"]["results"]
            keys = set(variables["keys"])
            return {"jobData": {"results": [r for r in rows if r["job"]["key"] in keys]}}
        if "IndeedEmployers" in query:
            return fx("employers")
        raise AssertionError(query[:80])

    pages = {"/cmp/Google": "company_overview", "/cmp/Google/reviews": "company_reviews",
             "/cmp/Google/salaries": "company_salaries", "/cmp/Google/salaries/Software-Engineer": "company_title_salaries",
             "/cmp/Google/faq": "company_questions", "/cmp/Google/locations": "company_locations",
             "/companies/search": "company_search"}

    def comp_data(path, country="US", params=None, label=None):
        calls.setdefault("pages", []).append((path, params))
        if path not in pages:
            raise fetch.IndeedNotFound(path)
        return fx(pages[path])

    monkeypatch.setattr(fetch, "graphql", graphql)
    monkeypatch.setattr(fetch, "comp_data", comp_data)
    monkeypatch.setattr(fetch, "next_data", lambda path, country="US", params=None, label=None: fx("career_salaries"))
    monkeypatch.setattr(fetch, "autocomplete", lambda kind, query, country="US", language="en", count=10:
                        fx("autocomplete_company") if kind == "company" else fx("autocomplete_what"))
    monkeypatch.setattr(fetch, "shared_raw", lambda name, params, build, ttl: build())
    jobs._chunks.clear()
    return calls


def test_search_pages_share_one_chunk(offline):
    page1 = jobs.search(query="nurse", location="Chicago, IL")
    page2 = jobs.search(query="nurse", location="Chicago, IL", page=2)
    assert len(page1["jobs"]) == 20 and len(page2["jobs"]) == 10
    assert page1["jobs"][0]["id"] != page2["jobs"][0]["id"]
    assert len(offline["graphql"]) == 1                     # one upstream chunk served both pages
    assert page1["pagination"]["total_pages"] == 50 and page1["pagination"]["total_count"] > 1000
    variables = offline["graphql"][0][1]
    assert variables["location"] == {"where": "Chicago, IL", "radius": 25, "radiusUnit": "MILES"}


def test_search_filters_and_company(offline):
    jobs.search(query="nurse", country="DE", date_posted="last_7_days", job_type="part_time", work_setting="remote",
                experience_level="entry_level", min_salary=50000, company={"slug": None, "id": "d5cd619626c9f6f7"},
                attributes=["X62BT"], location="Berlin")
    variables = offline["graphql"][-1][1]
    assert variables["location"]["radiusUnit"] == "KILOMETERS"
    kinds = [list(f)[0] for f in variables["filters"]]
    assert kinds == ["date", "keyword", "range", "keyword"]
    assert variables["filters"][1]["keyword"]["keys"] == ["75GKK", "DSQF7", "Y4JG9", "X62BT"]
    assert variables["filters"][3]["keyword"] == {"field": "indeedEmployerKey", "keys": ["d5cd619626c9f6f7"]}


def test_search_last_page_when_cursor_runs_out(offline):
    out = jobs.search(query="nurse", page=6)                 # chunk 1 = the fixture again, with no next cursor
    assert out["pagination"]["total_pages"] == 7 and len(out["jobs"]) == 20
    assert jobs.search(query="nurse", page=9)["jobs"] == []


def test_details_batch_and_not_found(offline):
    assert jobs.details("4322ca654f18afae")["company"]["ratings"]
    out = jobs.batch(["bca244a4074f26cb", "0000000000000000", "4322ca654f18afae"])
    assert [j["id"] for j in out["jobs"]] == ["bca244a4074f26cb", "4322ca654f18afae"] and out["not_found"] == ["0000000000000000"]
    with pytest.raises(fetch.IndeedNotFound):
        jobs.details("0000000000000000")
    assert jobs.filters(query="data analyst")["attributes"]
    # the whole US index cannot be faceted upstream: nothing to narrow it -> last 30 days
    out = jobs.filters()
    assert out["search"]["date_posted"] == "last_30_days"
    assert offline["graphql"][-1][1]["filters"] == [{"date": {"field": "dateOnIndeed", "start": "30d"}}]
    assert jobs.filters(country="GB")["search"]["date_posted"] is None


def test_company_endpoints(offline):
    google = {"slug": "Google", "id": None}
    assert companies.details(google)["social_links"]["facebook"]
    out = companies.reviews(google, page=2, sort="oldest", topic="management", review_country="IN", job_title="SWE")
    path, params = offline["pages"][-1]
    assert path == "/cmp/Google/reviews" and params["start"] == 20 and params["sort"] == "date_asc"
    assert params["ftopic"] == "mgmt" and params["fcountry"] == "IN" and params["fjobtitle"] == "SWE"
    assert out["pagination"]["page"] == 2
    companies.reviews(google, location="Mountain View, CA")
    assert offline["pages"][-1][1]["fcountry"] == "US"
    salaries_out = companies.salaries(google, location="Mountain View, CA", job_category="techsoftware")
    assert offline["pages"][-1][1] == {"location": "US/CA/Mountain View", "job_category": "techsoftware"}
    assert salaries_out["salaries"]
    with pytest.raises(ValueError):
        companies.salaries(google, location="Atlantis")
    assert companies.salaries(google, job_title="software engineer")["average_salary"]
    assert companies.questions(google)["questions"] and companies.locations(google)["states"]
    assert companies.search("amazon")["companies"]
    assert companies.slug_of({"slug": None, "id": "d5cd619626c9f6f7"}, "US") == "Google"
    assert companies.employer_id(google) == "d5cd619626c9f6f7"         # from the company autocomplete


def test_salaries_autocomplete_countries(offline):
    assert salaries.job_title("software-engineer")["salaries"]["yearly"]
    out = search.autocomplete("goo", type="companies", limit=3)
    assert len(out["suggestions"]) == 3 and out["suggestions"][0]["id"]
    countries = search.countries()["countries"]
    assert len(countries) == 62 and {"code": "GB", "name": "United Kingdom", "site": "https://uk.indeed.com"} in countries


def test_graphql_error_classification():
    with pytest.raises(fetch.IndeedBadRequest):
        fetch._classify_graphql(400, json.dumps({"errors": [{"message": "Request country ZZ does not correspond to a valid Indeed site."}]}), "t")
    with pytest.raises(fetch.IndeedBadRequest):
        fetch._classify_graphql(200, json.dumps({"data": None, "errors": [{"message": "Exception while fetching data (/jobSearch) : Invalid range filter.",
                                                                            "extensions": {"code": "BAD_USER_INPUT"}}]}), "t")
    with pytest.raises(fetch.IndeedQueryError):
        fetch._classify_graphql(400, json.dumps({"errors": [{"message": "Cannot query field", "extensions": {"code": "GRAPHQL_VALIDATION_FAILED"}}]}), "t")
    with pytest.raises(fetch.IndeedBlocked):
        fetch._classify_graphql(429, "", "t")
    # partial field errors next to real data are ignored
    data = fetch._classify_graphql(200, json.dumps({"data": {"jobSearch": {"results": []}}, "errors": [{"message": "x"}]}), "t")
    assert data == {"jobSearch": {"results": []}}


def test_page_classification():
    with pytest.raises(fetch.IndeedBlocked):
        fetch.classify_page(403, {"cf-mitigated": "challenge"}, "<title>Just a moment...</title>", "https://www.indeed.com/cmp/x", "t")
    with pytest.raises(fetch.IndeedBlocked):
        fetch.classify_page(401, {}, "Authenticating", "https://www.indeed.com/cmp/x", "t")
    with pytest.raises(fetch.IndeedBlocked):
        fetch.classify_page(200, {}, "", "https://secure.indeed.com/auth?x", "t")
    with pytest.raises(fetch.IndeedNotFound):
        fetch.classify_page(404, {}, "<title>Not Found | Indeed.com</title>", "https://www.indeed.com/cmp/x", "t")
    assert fetch.classify_page(200, {}, "<html>ok</html>", "https://www.indeed.com/cmp/x", "t") == "<html>ok</html>"


def test_build_filters_none_when_empty():
    assert gql.build_filters() is None
    assert gql.search_variables() == {"limit": 100, "sort": "RELEVANCE"}
