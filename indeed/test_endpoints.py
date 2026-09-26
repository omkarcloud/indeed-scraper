"""Live endpoint smoke tests: one call per /indeed/* route against a running
service, with example values proven to return data (2026-09-26). The
listing tooling (derive_facts.py) reads each route's FIRST call from this
file's AST as its working example, so the values stay literals.

Skipped unless INDEED_BASE points at a running service:

    SCRAPERS_PORT=6048 ONLY_SCRAPER=indeed python run.py
    INDEED_BASE=http://127.0.0.1:6048 python -m pytest indeed/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("INDEED_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set INDEED_BASE to run live endpoint tests")


def call(path, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=300)
    assert resp.status_code == 200, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def status(path, **params):
    from curl_cffi import requests
    return requests.get(BASE + path, params=params, timeout=300).status_code


def test_job_search():
    body = call("/indeed/jobs/search", query="python developer", location="New York, NY")
    assert body["count"] > 100 and len(body["jobs"]) == 20 and body["total_pages"] == 50 and body["next"]
    job = body["jobs"][0]
    assert len(job["id"]) == 16 and job["title"] and job["description"] and job["company"]["name"]
    page3 = call("/indeed/jobs/search", query="python developer", location="New York, NY", page=3)
    assert page3["jobs"][0]["id"] not in {j["id"] for j in body["jobs"]}
    body = call("/indeed/jobs/search", query="nurse", location="Chicago, IL", date_posted="last_7_days",
                job_type="full_time", min_salary=60000, sort="date")
    assert body["jobs"] and all("Full-time" in j["job_types"] for j in body["jobs"])
    body = call("/indeed/jobs/search", query="customer service", work_setting="remote", experience_level="entry_level")
    assert all(j["work_setting"] == "remote" for j in body["jobs"])
    body = call("/indeed/jobs/search", query="developer", location="London", country="GB")
    assert body["jobs"][0]["link"].startswith("https://uk.indeed.com/viewjob?jk=")
    body = call("/indeed/jobs/search", company="Google", location="Mountain View, CA")
    assert all(j["company"]["name"] == "Google" for j in body["jobs"])


def test_job_filters():
    body = call("/indeed/jobs/filters", query="data analyst", location="Austin, TX")
    assert body["total_count"] and body["date_posted"]["last_30_days"] and len(body["attributes"]) == 25
    assert body["occupations"] and body["cities"]


def test_job_details_and_batch():
    job_id = call("/indeed/jobs/search", query="registered nurse", location="Houston, TX")["jobs"][0]["id"]
    body = call("/indeed/jobs/details", job=f"https://www.indeed.com/viewjob?jk={job_id}")
    assert body["id"] == job_id and body["description_html"] and body["location"]["city"]
    body = call("/indeed/jobs/batch", jobs=f"{job_id},0000000000000000")
    assert [j["id"] for j in body["jobs"]] == [job_id] and body["not_found"] == ["0000000000000000"]
    assert status("/indeed/jobs/details", job="0000000000000000") == 404
    assert status("/indeed/jobs/details", job="not a job") == 400


def test_companies():
    body = call("/indeed/companies/search", query="amazon")
    assert body["companies"][0]["slug"] == "Amazon.com"
    body = call("/indeed/companies/details", company="Google")
    assert body["id"] == "d5cd619626c9f6f7" and body["rating"] and body["ceo"]["name"] and body["similar_companies"]
    assert call("/indeed/companies/details", company="Tesco", country="GB")["link"] == "https://uk.indeed.com/cmp/Tesco"
    assert status("/indeed/companies/details", company="this-company-does-not-exist-xyz") == 404


def test_company_reviews():
    body = call("/indeed/companies/reviews", company="https://www.indeed.com/cmp/Google/reviews")
    assert body["count"] > 1000 and len(body["reviews"]) == 20 and body["rating_distribution"]
    body = call("/indeed/companies/reviews", company="Google", sort="lowest_rating", location="Mountain View, CA")
    assert all(r["rating"] == 1 for r in body["reviews"][:5])
    body = call("/indeed/companies/reviews", company="Siemens", country="DE", page=2)
    assert body["reviews"] and body["reviews"][0]["date"]


def test_company_salaries():
    body = call("/indeed/companies/salaries", company="Google")
    assert body["salary_count"] > 1000 and len(body["salaries"]) >= 50
    body = call("/indeed/companies/salaries", company="Google", job_title="Software Engineer")
    assert body["average_salary"] and body["distribution"] and body["top_paying_cities"]
    body = call("/indeed/companies/salaries", company="Google", location="Mountain View, CA", job_category="Software Development")
    assert body["location"] == "Mountain View, CA" and body["salaries"]
    assert status("/indeed/companies/salaries", company="Google", location="Atlantis") == 400


def test_company_questions_locations_jobs():
    body = call("/indeed/companies/questions", company="Google")
    assert body["count"] > 50 and body["questions"][0]["question"]
    assert call("/indeed/companies/questions", company="Google", topic="hiring_process")["questions"]
    body = call("/indeed/companies/locations", company="Google")
    assert body["states"] and body["cities"]
    body = call("/indeed/companies/jobs", company="Amazon.com", location="Seattle, WA")
    assert body["count"] > 100 and all(j["company"]["name"] == "Amazon.com" for j in body["jobs"])


def test_career_salaries():
    body = call("/indeed/salaries", job_title="Software Engineer")
    assert body["salaries"]["yearly"]["median"] > 50000 and body["top_paying_cities"] and body["salary_by_state"]
    body = call("/indeed/salaries", job_title="registered nurse", location="Houston, TX")
    assert body["location"]["name"] == "Houston, TX" and body["national_salaries"]
    assert call("/indeed/salaries", job_title="data analyst", location="London", country="GB")["currency"] == "GBP"


def test_autocomplete_and_countries():
    body = call("/indeed/autocomplete", query="pyth")
    assert "python" in body["suggestions"]
    body = call("/indeed/autocomplete", query="goo", type="companies")
    assert body["suggestions"][0]["id"] and body["suggestions"][0]["link"]
    assert call("/indeed/autocomplete", query="lon", type="locations", country="GB")["suggestions"]
    assert len(call("/indeed/countries")["countries"]) == 62
