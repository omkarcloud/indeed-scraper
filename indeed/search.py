"""/indeed/autocomplete and /indeed/countries."""
from indeed import fetch
from indeed import parsers as P
from indeed import refdata

# public type -> autocomplete.indeed.com suggestion kind
AUTOCOMPLETE_TYPES = {"job_titles": "what", "companies": "company", "locations": "location", "skills": "skill"}


def autocomplete(query, type="job_titles", country="US", limit=10):
    """Search-box suggestions: job titles / keywords, companies (with their
    page and employer id), locations or skills."""
    kind = AUTOCOMPLETE_TYPES[type]
    rows = fetch.autocomplete(kind, query, country, count=limit)
    return {"query": query, "type": type, "country": country,
            "suggestions": P.autocomplete(kind, rows, country)[:limit]}


def countries():
    """Every country Indeed runs a site for (valid `country` values)."""
    return {"countries": [{"code": code, "name": name, "site": f"https://{host}"}
                          for code, (name, host) in sorted(refdata.COUNTRIES.items(), key=lambda x: x[1][0])]}
