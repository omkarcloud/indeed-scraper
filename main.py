"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does (paginated ones carry a
`pagination` block instead of the flat count/next/previous fields); results
are written to output/*.json.
"""
import json
import os

from indeed import companies, jobs, salaries
from indeed.refs import resolve_company, resolve_job_title

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # 20 jobs per page with full descriptions, salaries and company ratings
    save("jobs_software_engineer_sf.json", jobs.search(query="software engineer", location="San Francisco, CA"))

    # a company name, an indeed.com/cmp/ link or an employer ID
    save("company_google.json", companies.details(resolve_company("Google")))

    # pay for any job title: median and range per hour to year, by state, top cities and companies
    save("salaries_software_engineer.json", salaries.job_title(resolve_job_title("Software Engineer")))
