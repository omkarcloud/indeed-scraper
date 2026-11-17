"""Indeed transport: plain curl_cffi, validated 2026-09-26.

Surfaces:

  graphql(query, country)   apis.indeed.com/graphql — the GraphQL API of
                            Indeed's iOS app (its public app key + headers
                            below). jobSearch (100 jobs / call, cursor
                            pagination to ~1,000, facets, filters) and jobData
                            (jobs by key, any country) serve every /indeed/jobs/*
                            route; employers(keys) serves employer profiles.
                            No Cloudflare, no rate limit seen: direct egress,
                            one retry on a residential exit after a failure.
  page(path, country)       www.indeed.com (or a country host) SSR pages behind
                            Cloudflare: /cmp/<slug>[/reviews|/salaries|/faq|
                            /locations], /companies/search, /career/<t>/salaries.
                            comp_data() reads <script id="comp-initialData">,
                            next_data() reads __NEXT_DATA__.props.pageProps.
  autocomplete(kind, ...)   autocomplete.indeed.com/api/v0/suggestions/<kind>
                            (what / company / location / skill), no Cloudflare.

Cloudflare answers Chrome TLS with a managed challenge (403, cf-mitigated:
challenge) on every proxy exit tried (residential and datacenter),
but lets Safari-iOS TLS through on ~85% of residential exits. So page() runs
curl_cffi impersonate="safari_ios" on a shared pool of sticky residential
exits (config.indeed_web_proxy), retires an exit on its first challenge and
retries on a fresh one up to config.INDEED_WEB_MAX_ATTEMPTS times; when every
attempt was challenged, one headful patchright Chrome on a fresh exit loads
the page, clicks Turnstile if shown, and hands back the rendered HTML.

Not used: the /jobs search page (page 2+ is a login wall for every anonymous
client, real Chrome included) and /viewjob (Cloudflare-challenged or an
Indeed bot-detection login on every exit) — GraphQL replaces both.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  IndeedUpstreamError  transport failure / 5xx / unexpected body — retryable
  IndeedBlocked        Cloudflare challenge on every exit — retryable
  IndeedBadRequest     Indeed rejected the params                   — never retried
  IndeedNotFound       no such job / company / page                 — never retried
"""
import json
import fastjson
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import browser_client
import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from indeed import shared as S
from scraper_utils import debug, fanout, memo, sessions

GRAPHQL_URL = "https://apis.indeed.com/graphql"
AUTOCOMPLETE_URL = "https://autocomplete.indeed.com/api/v0/suggestions/{kind}"
TIMEOUT = (10, 35)            # (connect, read): a dead exit fails fast
WEB_IMPERSONATE = "safari_ios"

# The Indeed iOS app's public GraphQL key and identity headers (the same
# values every open-source Indeed client uses). The job-retrieval subgraph
# answers this key; the website's own keys cannot run jobSearch.
APP_API_KEY = "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8"
GRAPHQL_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json",
    "indeed-api-key": APP_API_KEY,
    "indeed-locale": "en-US",          # English attribute labels in every country
    "accept-language": egress.site_accept_language("indeed"),
    "user-agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"),
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}
PAGE_HEADERS = {"accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": egress.site_accept_language("indeed")}
JSON_HEADERS = {"accept": "application/json, text/plain, */*", "accept-language": egress.site_accept_language("indeed")}

CF_MARKERS = ("just a moment", "security check", "attention required", "cf-chl", "challenge-platform")
COMP_DATA_RE = re.compile(r'<script id="comp-initialData" type="application/json">(.*?)</script>', re.S)
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


class IndeedUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected body — retryable."""


class IndeedBlocked(IndeedUpstreamError, Blocked):
    """Cloudflare challenge / 429 that exit rotation could not get past."""


class IndeedBadRequest(BadRequest):
    """Indeed rejected the params (unknown country, bad filter value)."""


class IndeedNotFound(NotFound):
    """No such job / company / page — never retried."""


class IndeedQueryError(IndeedUpstreamError):
    """Indeed refused our GraphQL document (schema drift) — a retry cannot help."""


def dump_debug(name, text):
    """Write a raw response to $INDEED_DEBUG_DIR/<name>.txt."""
    debug.dump("INDEED_DEBUG_DIR", name, text)


# ---- curl sessions ---------------------------------------------------------------------
# curl handles are per thread (never shared across threads), keyed by exit.

_local = threading.local()


def _sessions():
    return sessions.thread_store(_local)


def _session(key, proxy, impersonate):
    from curl_cffi import requests as curl_requests
    store = _sessions()
    sess = store.get(key)
    if sess is None:
        sess = curl_requests.Session(impersonate=impersonate)
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        store[key] = sess
        while len(store) > 6:
            _, old = store.popitem(last=False)
            try:
                old.close()
            except Exception:
                pass
    else:
        store.move_to_end(key)
    return sess


def _drop_session(key):
    sessions.drop_keyed(_sessions(), key)


# ---- GraphQL ------------------------------------------------------------------------------

def _graphql_errors(body):
    return [e for e in (body.get("errors") or []) if isinstance(e, dict)]


def _classify_graphql(status, text, label):
    """-> the `data` object, or raise the failure the response represents."""
    if status in (403, 429):
        raise IndeedBlocked(f"HTTP {status} from apis.indeed.com on {label}")
    if status >= 500:
        raise IndeedUpstreamError(f"HTTP {status} from apis.indeed.com on {label}")
    try:
        body = fastjson.loads(text or "")
    except ValueError:
        dump_debug("graphql_non_json", text)
        raise IndeedUpstreamError(f"non-JSON GraphQL answer (HTTP {status}) on {label}")
    errors = _graphql_errors(body)
    messages = "; ".join(str(e.get("message", ""))[:300] for e in errors)
    if "does not correspond to a valid Indeed site" in messages:
        raise IndeedBadRequest("Indeed has no site for this country.")
    data = body.get("data")
    if status == 400 or not isinstance(data, dict) or not any(v is not None for v in data.values()):
        codes = {str((e.get("extensions") or {}).get("code")) for e in errors}
        if "BAD_USER_INPUT" in codes:
            clean = re.sub(r"^Exception while fetching data \([^)]*\) : ", "", messages)
            raise IndeedBadRequest(clean or "Indeed rejected the search parameters.")
        dump_debug("graphql_error", text)
        if codes & {"GRAPHQL_VALIDATION_FAILED", "GRAPHQL_PARSE_FAILED", "FORBIDDEN"}:
            raise IndeedQueryError(f"Indeed refused the query on {label}: {messages[:300]}")
        raise IndeedUpstreamError(f"GraphQL error on {label}: {messages[:300] or f'HTTP {status}'}")
    return data


def graphql(query, variables=None, country="US", label="graphql"):
    """POST one GraphQL document for `country` -> its `data` object. Partial
    field errors next to real data are ignored (Indeed reports optional
    sub-fields it will not serve as errors)."""
    headers = dict(GRAPHQL_HEADERS, **{"indeed-co": (country or "US").upper()})
    payload = {"query": query, "variables": variables or {}}
    attempts = max(1, int(config.INDEED_GRAPHQL_MAX_ATTEMPTS))
    last = None
    for attempt in range(1, attempts + 1):
        proxy = config.indeed_graphql_proxy(fallback=attempt > 1)
        key = f"gql:{proxy or 'direct'}"
        sess = _session(key, proxy, WEB_IMPERSONATE)
        try:
            resp = sess.post(GRAPHQL_URL, headers=headers, json=payload, timeout=TIMEOUT)
        except Exception as e:
            _drop_session(key)
            last = IndeedUpstreamError(f"GraphQL request failed on {label}: {type(e).__name__}: {e}")
        else:
            try:
                return _classify_graphql(resp.status_code, resp.text, label)
            except (IndeedBadRequest, IndeedNotFound, IndeedQueryError):
                raise
            except IndeedUpstreamError as e:
                _drop_session(key)
                last = e
        print(f"indeed: GraphQL attempt {attempt}/{attempts} on {label} failed: {last}")
        if attempt < attempts:
            time.sleep(0.4 * attempt)
    raise last


# ---- web pages: exit pool ------------------------------------------------------------------

class _Exit:
    """One sticky exit and a serial key for its curl sessions (a new exit
    always opens a new tunnel, even when exits share one rotating URL)."""
    __slots__ = ("proxy", "used", "key")
    _serial = 0
    _serial_lock = threading.Lock()

    def __init__(self, proxy):
        self.proxy = proxy
        self.used = 0
        with _Exit._serial_lock:
            _Exit._serial += 1
            self.key = f"web:{_Exit._serial}:{proxy or 'direct'}"


_pool_lock = threading.Lock()
_pool = []


def _budget():
    return max(1, int(config.INDEED_WEB_REQUESTS_PER_EXIT))


def _take_exit(fresh=False):
    with _pool_lock:
        if not fresh:
            for ex in _pool:
                if ex.used < _budget():
                    ex.used += 1
                    if ex.used >= _budget():
                        _pool.remove(ex)
                    return ex
        ex = _Exit(config.indeed_web_proxy())
        ex.used = 1
        if _budget() > 1:
            _pool.append(ex)
        return ex


def _retire(ex):
    with _pool_lock:
        if ex in _pool:
            _pool.remove(ex)
    _drop_session(ex.key)


def is_challenged(status, headers, text):
    if (headers or {}).get("cf-mitigated") == "challenge":
        return True
    head = (text or "")[:4000].lower()
    return status in (403, 429, 503) and any(m in head for m in CF_MARKERS)


def classify_page(status, headers, text, final_url, label):
    """Raise the failure a page response represents, or return its HTML."""
    if is_challenged(status, headers, text):
        raise IndeedBlocked(f"Cloudflare challenge (HTTP {status}) on {label}")
    if "secure.indeed.com" in (final_url or "") or "/account/login" in (final_url or ""):
        raise IndeedBlocked(f"login wall on {label}")
    if status == 401:
        # Indeed's own bot check ("Authenticating…" page) on a flagged exit
        raise IndeedBlocked(f"Indeed bot check (HTTP 401) on {label}")
    if status in (404, 410):
        raise IndeedNotFound(f"Indeed has no page for {label}")
    if status == 429:
        raise IndeedBlocked(f"HTTP 429 on {label}")
    if status != 200:
        raise IndeedUpstreamError(f"HTTP {status} on {label}")
    return text or ""


def _curl_page(url, label, fresh):
    ex = _take_exit(fresh=fresh)
    sess = _session(ex.key, ex.proxy, WEB_IMPERSONATE)
    try:
        resp = sess.get(url, headers=PAGE_HEADERS, timeout=TIMEOUT, allow_redirects=True)
    except Exception as e:
        _retire(ex)
        raise IndeedUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}")
    try:
        return classify_page(resp.status_code, dict(resp.headers), resp.text, str(resp.url), label)
    except IndeedBlocked:
        _retire(ex)
        dump_debug("challenged", resp.text)
        raise


# ---- web pages: browser fallback (on the browser box) ------------------------------------------

# Sticky exits for the box browsers: one proxy URL = one kept Chrome on the
# box, parked on robots.txt with its Turnstile clearance and retired after
# max_uses pages (recipes/indeed.py, = INDEED_WEB_REQUESTS_PER_EXIT). Until
# 2026-11-04 every fallback call minted a fresh exit, so every call launched
# a Chrome and cleared Turnstile again. burst=True: INDEED_BROWSER_SLOTS x
# BROWSER_BURST_FACTOR candidates; the box opens the extra ones with headroom.
_BROWSER_EXITS = browser_client.ExitPool("indeed", config.indeed_web_proxy,
                                         size=lambda: config.INDEED_BROWSER_SLOTS, burst=True,
                                         uses_per_exit=lambda: config.INDEED_WEB_REQUESTS_PER_EXIT)


def _browser_page(url, label):
    """On the browser box (recipes/indeed.py): a Chrome on one of the sticky
    exits (_BROWSER_EXITS) loads the page, clicks Turnstile when shown and
    returns the HTML once the real page is up (404 when Indeed has no such
    page). A refused exit (Indeed's 401 check on a flagged exit shows as a
    settle timeout) is rotated. Chrome left GKE 2026-10-22."""
    try:
        _proxy, res = _BROWSER_EXITS.fetch_any("indeed", url=url)
    except browser_client.BoxRefused as e:
        if e.candidate is not None:
            _BROWSER_EXITS.rotate(e.proxy)
        raise IndeedBlocked(f"{label}: refused in the box browser: {e}") from e
    except browser_client.BoxUnavailable as e:
        raise IndeedUpstreamError(f"{label}: browser box unavailable: {e}") from e
    if int(res.get("status") or 0) == 404:
        raise IndeedNotFound(f"Indeed has no page for {label}")
    return classify_page(200, {}, res.get("body") or "", url, label)


# ---- web pages: public ------------------------------------------------------------------------

def page(path, country="US", params=None, label=None):
    """GET an Indeed page on the country's host -> HTML. Non-US sites get
    hl=en: English UI, so dates and labels parse the same everywhere."""
    query = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    if (country or "US").upper() != "US":
        query.setdefault("hl", "en")
    url = f"https://{S.host(country)}{path}" + (("?" + urlencode(query)) if query else "")
    label = label or path
    last = None
    blocked_only = True
    attempts = max(1, int(config.INDEED_WEB_MAX_ATTEMPTS))
    for attempt in range(1, attempts + 1):
        try:
            return _curl_page(url, label, fresh=attempt > 1)
        except (IndeedNotFound, IndeedBadRequest):
            raise
        except IndeedBlocked as e:
            last = e
        except IndeedUpstreamError as e:
            last = e
            blocked_only = False
        print(f"indeed: attempt {attempt}/{attempts} on {label} failed: {last}")
        if attempt < attempts:
            time.sleep(0.3 * attempt)
    if blocked_only and config.INDEED_WEB_BROWSER_FALLBACK:
        print(f"indeed: every curl attempt on {label} was challenged; trying a browser")
        try:
            return _browser_page(url, label)
        except (IndeedNotFound, IndeedBadRequest):
            raise
        except Exception as e:
            print(f"indeed: browser fallback failed on {label}: {type(e).__name__}: {e}")
            raise IndeedBlocked(f"{label}: challenged on {attempts} exits and in a browser") from e
    raise last


def extract_comp_data(html):
    match = COMP_DATA_RE.search(html or "")
    if not match:
        return None
    try:
        return fastjson.loads(match.group(1))
    except ValueError:
        return None


def comp_data(path, country="US", params=None, label=None):
    """A company-pages SSR page -> its comp-initialData object."""
    label = label or path
    html = page(path, country, params, label)
    data = extract_comp_data(html)
    if not isinstance(data, dict):
        dump_debug("no_comp_data", html)
        raise IndeedUpstreamError(f"no page data on {label} (layout changed?)")
    return data


def extract_next_data(html):
    match = NEXT_DATA_RE.search(html or "")
    if not match:
        return None
    try:
        return ((fastjson.loads(match.group(1)).get("props") or {}).get("pageProps")) or None
    except ValueError:
        return None


def next_data(path, country="US", params=None, label=None):
    """A Next.js page (career salaries) -> __NEXT_DATA__.props.pageProps."""
    label = label or path
    html = page(path, country, params, label)
    props = extract_next_data(html)
    if not isinstance(props, dict):
        dump_debug("no_next_data", html)
        raise IndeedUpstreamError(f"no page data on {label} (layout changed?)")
    if props.get("statusCode") in (404, 410):
        raise IndeedNotFound(f"Indeed has no page for {label}")
    return props


# ---- autocomplete ---------------------------------------------------------------------------------

def autocomplete(kind, query, country="US", language="en", count=10):
    """autocomplete.indeed.com suggestions -> the parsed JSON list."""
    from curl_cffi import requests as curl_requests
    url = AUTOCOMPLETE_URL.format(kind=kind)
    params = {"query": query, "country": country, "language": language, "count": count}
    label = f"autocomplete {kind}"
    last = None
    for proxy in (None, config.indeed_graphql_proxy(fallback=True)):
        try:
            resp = curl_requests.get(url, params=params, headers=JSON_HEADERS, impersonate=WEB_IMPERSONATE,
                                     timeout=TIMEOUT, proxies={"http": proxy, "https": proxy} if proxy else None)
        except Exception as e:
            last = IndeedUpstreamError(f"request failed on {label}: {type(e).__name__}: {e}")
            continue
        if resp.status_code == 400:
            raise IndeedBadRequest(f"Indeed rejected the autocomplete request: {resp.text[:200]}")
        if resp.status_code != 200:
            last = IndeedUpstreamError(f"HTTP {resp.status_code} on {label}")
            continue
        try:
            body = resp.json()
        except ValueError:
            last = IndeedUpstreamError(f"non-JSON body on {label}")
            continue
        return body if isinstance(body, list) else []
    raise last


# ---- memo + fan-out -----------------------------------------------------------------------------------
# Several routes read ONE upstream answer (a company overview page feeds
# details and the employer-id lookup; a search chunk of 100 jobs feeds five
# pages); this memo + the response cache let them share one fetch.
_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 600
MEMO_MAX = 256


def memoized(key, fn, ttl=MEMO_TTL):
    return memo.memoized(_memo, _memo_lock, MEMO_MAX, key, fn, ttl)


def shared_raw(name, params, build, ttl):
    """An upstream payload shared by several routes: in-process memo, then
    the response cache (pods share it), then build()."""
    from cache import cached_call
    seconds = ttl.total_seconds() if hasattr(ttl, "total_seconds") else ttl
    key = (name, json.dumps(params, sort_keys=True))
    return memoized(key, lambda: cached_call(f"indeed.raw.{name}", params, lambda **_: build(), ttl),
                    ttl=min(seconds, MEMO_TTL))


def run_parallel(fns, workers):
    """Run zero-arg callables in parallel; results align with `fns`. Each
    result is ("ok", value) or ("error", exception)."""
    return fanout.guarded_per_call(fns, workers)


if __name__ == "__main__":
    # Smoke test: python indeed/fetch.py
    data = graphql('query{ jobSearch(what:"nurse", limit:2){ results{ job{ key title } } } }', label="smoke")
    print(json.dumps(data)[:300])
    print(sorted(comp_data("/cmp/Google", label="smoke cmp").keys())[:8])
