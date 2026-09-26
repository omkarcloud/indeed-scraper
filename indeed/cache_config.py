"""Cache TTL per /indeed/* endpoint (cache.py, keyed on the validated params —
marshmallow fills the defaults, so an omitted param and its default share a
row).

Job listings churn hourly (new postings, expiries); a single job changes
rarely once posted; company pages, reviews and salary aggregates move daily
at most; career salary pages are refreshed about weekly."""
from datetime import timedelta

# --- raw upstream payloads shared by several routes (fetch.shared_raw) ----------
COMPANY_PAGE_RAW_CACHE = timedelta(days=2)     # /cmp/<slug> overview (details + employer id)
EMPLOYER_ID_CACHE = timedelta(days=30)         # slug -> employer id (never changes)
SALARY_FILTERS_RAW_CACHE = timedelta(days=3)   # /cmp/<slug>/salaries (location filter tree)

# --- jobs -------------------------------------------------------------------------
SEARCH_CACHE = timedelta(hours=1)
FILTERS_CACHE = timedelta(hours=1)
JOB_CACHE = timedelta(hours=6)

# --- companies ----------------------------------------------------------------------
COMPANY_SEARCH_CACHE = timedelta(days=3)
COMPANY_CACHE = timedelta(days=2)
REVIEWS_CACHE = timedelta(hours=12)
SALARIES_CACHE = timedelta(days=3)
QUESTIONS_CACHE = timedelta(days=2)
LOCATIONS_CACHE = timedelta(days=7)

# --- career salaries / autocomplete ----------------------------------------------------
CAREER_SALARIES_CACHE = timedelta(days=5)
AUTOCOMPLETE_CACHE = timedelta(days=7)
