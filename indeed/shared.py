"""Value helpers shared by every Indeed parser: numbers, text, dates, money,
salary periods and links. Pure functions, no network; every helper tolerates
None and junk."""
import html as html_lib
import re
from datetime import datetime, timedelta, timezone

from indeed import refdata

# ---- numbers --------------------------------------------------------------------------

def num(value):
    """int / float / numeric string ('1,234.5') -> float; bool, junk, NaN -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value == value else None
    try:
        out = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return out if out == out else None


def to_int(value):
    out = num(value)
    return int(round(out)) if out is not None else None


def rounded(value, digits=2):
    out = num(value)
    return round(out, digits) if out is not None else None


def amount(value):
    """A money amount: whole numbers as int, others rounded to cents."""
    out = num(value)
    if out is None:
        return None
    return int(out) if float(out).is_integer() else round(out, 2)


def positive(value):
    """Counts / ratings where 0 means "not given" -> None."""
    out = num(value)
    return out if out else None


def rating(value):
    """A 0-5 star rating rounded to 2 places; 0 / missing -> None."""
    out = num(value)
    return round(out, 2) if out else None


# ---- text -------------------------------------------------------------------------------

def text(value):
    """Whitespace-collapsed, HTML-unescaped string; '' -> None. Accepts the
    site's {"text": ...} wrappers."""
    if isinstance(value, dict):
        value = value.get("text")
    if value is None:
        return None
    out = " ".join(html_lib.unescape(str(value)).replace("\xa0", " ").split())
    return out or None


def multiline(value):
    """Like text() but keeps line breaks (review bodies, descriptions)."""
    if isinstance(value, dict):
        value = value.get("text")
    if value is None:
        return None
    lines = [" ".join(line.split()) for line in html_lib.unescape(str(value)).replace("\xa0", " ").splitlines()]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out or None


_SMALL_WORDS = {"and", "or", "of", "the", "in", "for", "to", "a", "on", "&"}


def code_label(value):
    """Indeed enum codes -> readable text: 'Iv1_EDUCATION_AND_SCHOOLS' ->
    'Education and Schools'; plain text passes through."""
    value = text(value)
    if not value:
        return None
    if not re.fullmatch(r"(?:[A-Za-z]+v\d+_)?[A-Z0-9_]+", value):
        return value
    words = re.sub(r"^[A-Za-z]+v\d+_", "", value).lower().split("_")
    return " ".join(w if (i and w in _SMALL_WORDS) else w.capitalize() for i, w in enumerate(words) if w) or None


def lower_snake(value):
    """'YEARLY' / 'Full-Time' -> 'yearly' / 'full_time'."""
    value = text(value)
    if not value:
        return None
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or None


# ---- dates -------------------------------------------------------------------------------

def iso_datetime_ms(ms):
    """Epoch milliseconds -> '2026-09-25T04:41:08Z' (UTC)."""
    value = num(ms)
    if not value or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def local_date_ms(ms):
    """Epoch ms of a LOCAL midnight (Indeed's datePublished) -> 'YYYY-MM-DD'.
    Shifting by 12 h before taking the UTC date gives the right calendar day
    for any UTC-12..+12 offset."""
    value = num(ms)
    if not value or value <= 0:
        return None
    try:
        return (datetime.fromtimestamp(value / 1000, tz=timezone.utc) + timedelta(hours=12)).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return None


_LONG_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")


def iso_date(value):
    """'September 22, 2026' / '2026-09-22T…' / '22 September 2026' -> '2026-09-22'.
    Dates in other languages -> None."""
    value = text(value)
    if not value:
        return None
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        return "-".join(match.groups())
    for fmt in _LONG_DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def iso_minute(value):
    """'2021-11-15T22:54Z' -> '2021-11-15T22:54:00Z'."""
    value = text(value)
    if not value:
        return None
    match = re.match(r"(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?", value)
    if not match:
        return iso_date(value)
    return f"{match.group(1)}T{match.group(2)}:{match.group(3)}:{match.group(4) or '00'}Z"


# ---- money / salary periods -------------------------------------------------------------------

PERIODS = {"HOUR": "hourly", "HOURLY": "hourly", "DAY": "daily", "DAILY": "daily", "WEEK": "weekly",
           "WEEKLY": "weekly", "MONTH": "monthly", "MONTHLY": "monthly", "YEAR": "yearly", "YEARLY": "yearly"}


def period(value):
    """HOUR / HOURLY / 'yearly' -> 'hourly' / 'yearly'; unknown -> None."""
    if not value:
        return None
    return PERIODS.get(str(value).strip().upper())


def currency_for(country):
    return refdata.CURRENCIES.get((country or "").upper())


_MONEY_RE = re.compile(r"(\d[\d.,\s]*)")


def money(value):
    """'$165,027' / '€ 52.000' / '$28.26' -> 165027 / 52000 / 28.26 (the first
    number in the string; thousands separators '.' or ',' handled when the
    last group has exactly 3 digits)."""
    value = text(value)
    if not value:
        return None
    match = _MONEY_RE.search(value)
    if not match:
        return None
    raw = match.group(1).strip().replace(" ", "").replace(" ", "")
    if "," in raw and "." in raw:
        # the right-most separator is the decimal point
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw or "." in raw:
        sep = "," if "," in raw else "."
        parts = raw.split(sep)
        # a trailing 3-digit group = thousands separators (also Indian 6,00,000)
        if len(parts) > 1 and len(parts[-1]) == 3 and all(1 <= len(p) <= 3 for p in parts):
            raw = "".join(parts)
        else:
            raw = raw.replace(",", ".")
    return amount(raw)


# ---- ranges from company-size codes --------------------------------------------------------------

_SIZE_UNITS = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000, "T": 1_000_000_000_000}


def _size_number(token):
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([KMBT]?)", token or "")
    if not match:
        return None
    return int(float(match.group(1)) * _SIZE_UNITS.get(match.group(2), 1))


def size_range(code):
    """Indeed's company-size codes -> {min, max}:
    ERv1_10000_PLUS -> {10000, None}; ERv1_1001_TO_5000 -> {1001, 5000};
    RRv1_OVER_10B -> {10e9, None}; RRv1_1M_TO_5M -> {1e6, 5e6};
    RRv1_LESS_THAN_1M -> {None, 1e6}. Unknown -> None."""
    if not code or not isinstance(code, str):
        return None
    body = re.sub(r"^[A-Za-z]+v\d+_", "", code.strip()).upper()
    match = re.fullmatch(r"(\w+?)_TO_(\w+)", body)
    if match:
        low, high = _size_number(match.group(1)), _size_number(match.group(2))
    elif body.endswith("_PLUS"):
        low, high = _size_number(body[:-5]), None
    elif body.startswith("OVER_") or body.startswith("MORE_THAN_"):
        low, high = _size_number(body.split("_")[-1]), None
    elif body.startswith("LESS_THAN_") or body.startswith("UNDER_"):
        low, high = None, _size_number(body.split("_")[-1])
    else:
        return None
    if low is None and high is None:
        return None
    return {"min": low, "max": high}


# ---- links -------------------------------------------------------------------------------------

def host(country):
    return refdata.COUNTRIES.get((country or "US").upper(), refdata.COUNTRIES["US"])[1]


def link(country, path):
    """A site-relative path (or absolute URL) -> absolute https link on the
    country's Indeed host; '' / None -> None."""
    path = text(path) if isinstance(path, str) else None
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    if path.startswith("//"):
        return "https:" + path
    return f"https://{host(country)}/{path.lstrip('/')}"


def job_link(country, key):
    return f"https://{host(country)}/viewjob?jk={key}" if key else None


def company_slug(path):
    """'/cmp/Google', '/cmp/Google/reviews', 'https://uk.indeed.com/cmp/Tesco?x' -> 'Google' / 'Tesco'."""
    path = text(path) if isinstance(path, str) else None
    if not path:
        return None
    match = re.search(r"/cmp/([^/?#]+)", path)
    return match.group(1) if match else None


def company_link(country, slug):
    return f"https://{host(country)}/cmp/{slug}" if slug else None


def country(code):
    """ISO code -> {"code", "name"}; unknown -> None."""
    code = (code or "").strip().upper()
    if len(code) != 2 or not code.isalpha():
        return None
    name = refdata.COUNTRIES.get(code, (None,))[0]
    return {"code": code, "name": name}
