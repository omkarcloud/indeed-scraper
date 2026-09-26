"""Configuration for the Indeed Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT          port the API listens on (default 8000)
    INDEED_PROXY  proxy URL, e.g. http://user:pass@host:port (default: none —
                  direct). Jobs come from Indeed's app API, which did not
                  rate-limit 60 parallel calls from one IP, so jobs never need
                  it. Company pages (profile, reviews, salaries, Q&A) sit
                  behind Cloudflare: from a home or office connection they
                  load directly, but from a cloud server you will want a
                  ROTATING residential proxy here — the scraper opens a new
                  connection (a new IP) after every block.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

INDEED_PROXY = os.environ.get("INDEED_PROXY") or None

# Company pages: switch to a new connection after this many pages, and try
# this many new connections after a block before giving up.
INDEED_WEB_REQUESTS_PER_EXIT = int(os.environ.get("INDEED_WEB_REQUESTS_PER_EXIT", "40"))
INDEED_WEB_MAX_ATTEMPTS = int(os.environ.get("INDEED_WEB_MAX_ATTEMPTS", "6"))
# The hosted version can fall back to a real browser; this package stays
# plain HTTP (no browser to install), so the fallback is off.
INDEED_WEB_BROWSER_FALLBACK = False
INDEED_BROWSER_CONCURRENCY = 1
INDEED_BROWSER_TIMEOUT = 45
# Indeed app API: attempts per call (a retry goes through INDEED_PROXY when set).
INDEED_GRAPHQL_MAX_ATTEMPTS = 3


def indeed_web_proxy():
    """The proxy for www.indeed.com company pages (None = direct)."""
    return INDEED_PROXY


def indeed_graphql_proxy(fallback=False):
    """The Indeed app API runs direct; a retry after a failure uses INDEED_PROXY."""
    return INDEED_PROXY if fallback else None
