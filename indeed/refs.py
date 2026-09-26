"""Indeed input parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrLinkField convention, never a sibling `url`/`id` pair).
Every resolver returns plain JSON values so validated params stay usable as
a response-cache key, and raises ValueError with a user-facing message.

  country    US | us | United States | uk | GB | uk.indeed.com
             | https://de.indeed.com/jobs?q=x              -> "US" / "GB" / "DE"
  job        bca244a4074f26cb | https://www.indeed.com/viewjob?jk=bca244a4074f26cb
             | …/jobs?q=x&vjk=… | …/rc/clk?jk=… | …/m/viewjob?jk=… | …/cmp/_/job?jk=…
                                                           -> "bca244a4074f26cb"
  company    Google | Amazon.com | Bank of America | https://www.indeed.com/cmp/Google/reviews
             | uk.indeed.com/cmp/Tesco | d5cd619626c9f6f7 (employer id)
                                                           -> {"slug": "Google", "id": None}
                                                              | {"slug": None, "id": "d5cd…"}
  job_title  Software Engineer | software-engineer | https://www.indeed.com/career/software-engineer/salaries
                                                           -> "software-engineer"
  location   (career salaries) New York, NY | CA | London | a /career/<t>/salaries/<seg> link
                                                           -> "New-York--NY" / "CA" / "London"
"""
import re
from urllib.parse import parse_qs, unquote, urlparse

from indeed import refdata

_KEY_RE = re.compile(r"^[0-9a-f]{16}$")
_SLUG_BAD = re.compile(r"[/?#\\<>\"]")


def _parse_url(value):
    """-> (host, path, query dict) when value looks like a URL/host path, else None."""
    raw = value.strip()
    low = raw.lower()
    if low.startswith("//"):
        raw = "https:" + raw
    elif not low.startswith(("http://", "https://")):
        head = low.split("/", 1)[0]
        if "indeed." not in head:
            return None
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if "indeed." not in host:
        raise ValueError("Must be an indeed.com link.")
    return host, unquote(parsed.path), parse_qs(parsed.query)


# ---- country -----------------------------------------------------------------------------

_COUNTRY_NAMES = {name.lower(): code for code, (name, _) in refdata.COUNTRIES.items()}
_COUNTRY_NAMES.update({"uk": "GB", "united states of america": "US", "usa": "US", "america": "US",
                       "great britain": "GB", "england": "GB", "korea": "KR", "czechia": "CZ",
                       "uae": "AE", "holland": "NL", "türkiye": "TR", "turkiye": "TR"})
COUNTRY_HINT = ("Must be an Indeed country: an ISO code (US, GB, IN, DE, …), its English name, or an "
                "indeed.com link on that country's site.")


def resolve_country(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COUNTRY_HINT)
    try:
        url = _parse_url(raw) if ("." in raw or "/" in raw) else None
    except ValueError:
        raise ValueError(COUNTRY_HINT)
    if url:
        label = url[0].split(".")[0]
        code = refdata.HOST_COUNTRIES.get(label)
        if code:
            return code
        raise ValueError(COUNTRY_HINT)
    low = raw.lower()
    if low in _COUNTRY_NAMES:
        return _COUNTRY_NAMES[low]
    code = raw.upper()
    if code in refdata.COUNTRIES:
        return code
    raise ValueError(f"Indeed has no site for '{raw}'. " + COUNTRY_HINT)


def country_of_link(value):
    """The country of an indeed.com link's host, or None."""
    try:
        url = _parse_url(value or "")
    except ValueError:
        return None
    return refdata.HOST_COUNTRIES.get(url[0].split(".")[0]) if url else None


# ---- jobs ----------------------------------------------------------------------------------

JOB_HINT = "Must be an Indeed job key (16 hex characters, e.g. bca244a4074f26cb) or an indeed.com job link."


def resolve_job(value):
    raw = (value or "").strip()
    if _KEY_RE.match(raw.lower()):
        return raw.lower()
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(JOB_HINT)
    if not url:
        raise ValueError(JOB_HINT)
    _, path, query = url
    for name in ("jk", "vjk", "jobKey", "jobkey"):
        for candidate in query.get(name, []):
            if _KEY_RE.match(candidate.strip().lower()):
                return candidate.strip().lower()
    match = re.search(r"[-/]([0-9a-f]{16})(?:[/?#]|$)", path.lower())
    if match:
        return match.group(1)
    raise ValueError(JOB_HINT)


# ---- companies ------------------------------------------------------------------------------

COMPANY_HINT = ("Must be an Indeed company page name as it appears in /cmp/<name> links (Google, "
                "Amazon.com), a company name, an indeed.com/cmp/ link or an Indeed employer id.")


def resolve_company(value):
    raw = (value or "").strip()
    if not raw:
        raise ValueError(COMPANY_HINT)
    if _KEY_RE.match(raw.lower()):
        return {"slug": None, "id": raw.lower()}
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(COMPANY_HINT)
    if url:
        match = re.search(r"/cmp/([^/?#]+)", url[1])
        if not match or match.group(1) == "_":
            raise ValueError("indeed.com links must be company pages (/cmp/<name>).")
        raw = match.group(1)
    slug = "-".join(raw.split())          # 'Bank of America' -> 'Bank-of-America'
    if not slug or _SLUG_BAD.search(slug) or len(slug) > 150:
        raise ValueError(COMPANY_HINT)
    return {"slug": slug, "id": None}


# ---- career salaries -------------------------------------------------------------------------

TITLE_HINT = "Must be a job title (Software Engineer) or an indeed.com/career/<title>/salaries link."


def resolve_job_title(value):
    raw = (value or "").strip()
    try:
        url = _parse_url(raw)
    except ValueError:
        raise ValueError(TITLE_HINT)
    if url:
        match = re.search(r"/career/([^/?#]+)", url[1])
        if not match:
            raise ValueError(TITLE_HINT)
        raw = match.group(1)
    slug = re.sub(r"[\s/]+", "-", raw.lower())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not slug or len(slug) > 120 or _SLUG_BAD.search(slug):
        raise ValueError(TITLE_HINT)
    return slug


def career_location_segment(value):
    """'New York, NY' -> 'New-York--NY'; 'CA' -> 'CA'; 'London' -> 'London';
    a /career/<t>/salaries/<seg> link -> its segment."""
    raw = (value or "").strip()
    if not raw:
        return None
    url = _parse_url(raw) if "indeed." in raw.lower() else None
    if url:
        match = re.search(r"/career/[^/]+/salaries/([^/?#]+)", url[1])
        if not match:
            raise ValueError("indeed.com links must be /career/<title>/salaries/<location> pages.")
        return match.group(1)
    parts = [" ".join(p.split()) for p in raw.split(",") if p.strip()]
    if not parts or _SLUG_BAD.search(raw):
        raise ValueError("Must be a city ('New York, NY'), a state code ('CA') or a city name ('London').")
    return "--".join(p.replace(" ", "-") for p in parts[:2])


def title_from_slug(slug):
    return " ".join(w.capitalize() for w in (slug or "").split("-") if w) or None
