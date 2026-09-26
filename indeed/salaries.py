"""/indeed/salaries — Indeed's career salary pages (/career/<title>/salaries
[/<location>]), a Next.js page read from __NEXT_DATA__: salary estimates for
every pay period, state map, top-paying cities and companies, related titles
and the skills / fields of study that pay more."""
from urllib.parse import quote

from indeed import fetch
from indeed import parsers as P


def job_title(job_title, location=None, country="US"):
    path = f"/career/{quote(job_title, safe='-+.')}/salaries" + (f"/{quote(location, safe='-')}" if location else "")
    props = fetch.next_data(path, country, label=f"career salaries {job_title}" + (f" in {location}" if location else ""))
    if not P.g(props, "localSalaryAggregate") and not P.g(props, "nationalSalaryAggregate"):
        raise fetch.IndeedNotFound(f"Indeed has no salary data for {job_title}" + (f" in {location}" if location else ""))
    return P.career_salaries(props, country, job_title)
