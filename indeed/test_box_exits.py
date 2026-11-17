"""The box browser's sticky exits (indeed/fetch.py _BROWSER_EXITS): one proxy
URL = one kept Chrome on the box, reused across calls (until 2026-11-04
every call minted a fresh exit and so a fresh Chrome); a refused exit is
rotated alone; the pod offers share x BROWSER_BURST_FACTOR candidates."""
import itertools

import pytest

import browser_client as bc
import config
from indeed import fetch as f
from scraper_utils.testing import hosted_only


@pytest.fixture
def box(monkeypatch):
    """A fake box: records every candidate list it was offered and answers
    with candidate 0, or refuses the candidate `refuse` names."""
    f._BROWSER_EXITS.reset()
    counter = itertools.count(1)
    monkeypatch.setattr(f._BROWSER_EXITS, "_mint", lambda: f"http://u:p@gw:{10000 + next(counter)}")
    state = {"offered": [], "refuse": None, "result": {"status": 200, "body": '<html>ok</html>', "headers": {}}}

    def fake_fetch_any(site, candidates, **kw):
        assert site == "indeed"
        state["offered"].append([p for p, _s in candidates])
        if state["refuse"] is not None:
            raise bc.BoxRefused("indeed/fetch: 502 recipe", candidate=state["refuse"])
        return 0, dict(state["result"])
    monkeypatch.setattr(bc, "fetch_any", fake_fetch_any)
    monkeypatch.setattr(f, "classify_page", lambda status, headers, text, final_url, label: text)
    yield state
    f._BROWSER_EXITS.reset()


@hosted_only
def test_the_same_exit_serves_every_call(box, monkeypatch):
    monkeypatch.setattr(config, "BROWSER_BURST_FACTOR", 1)
    f._browser_page("https://www.indeed.com/cmp/x", "x")
    f._browser_page("https://www.indeed.com/cmp/x", "x")
    assert len(box["offered"]) == 2 and box["offered"][0] == box["offered"][1]
    assert box["offered"][0] == f._BROWSER_EXITS.current()          # minted once, reused


@hosted_only
def test_a_refusal_rotates_only_the_exit_it_happened_on(box, monkeypatch):
    monkeypatch.setattr(config, "BROWSER_BURST_FACTOR", 2)
    f._browser_page("https://www.indeed.com/cmp/x", "x")
    before = f._BROWSER_EXITS.current()
    box["refuse"] = 1
    with pytest.raises(f.IndeedBlocked):
        f._browser_page("https://www.indeed.com/cmp/x", "x")
    after = f._BROWSER_EXITS.current()
    assert after[0] == before[0] and after[1] != before[1] and len(after) == len(before)


@hosted_only
def test_the_pod_offers_share_times_the_burst_factor(box, monkeypatch):
    monkeypatch.setattr(config, "BROWSER_BURST_FACTOR", 4)
    f._browser_page("https://www.indeed.com/cmp/x", "x")
    assert len(box["offered"][-1]) == config.INDEED_BROWSER_SLOTS * 4 == f._BROWSER_EXITS.share() * 4
    f._BROWSER_EXITS.reset()
    monkeypatch.setattr(config, "BROWSER_BURST_FACTOR", 1)
    f._browser_page("https://www.indeed.com/cmp/x", "x")
    assert len(box["offered"][-1]) == config.INDEED_BROWSER_SLOTS


def test_an_exit_is_rotated_after_its_use_budget(box, monkeypatch):
    """The pod retires the EXIT after INDEED_WEB_REQUESTS_PER_EXIT pages, so the
    relaunch is on a fresh IP (a box-side max_uses would relaunch on the
    spent one)."""
    import config
    monkeypatch.setattr(config, "INDEED_WEB_REQUESTS_PER_EXIT", 2)
    f._BROWSER_EXITS.reset()
    f._BROWSER_EXITS.all()
    first = f._BROWSER_EXITS.current()[0]
    f._browser_page("https://www.indeed.com/cmp/x", "x")
    assert f._BROWSER_EXITS.current()[0] == first
    f._browser_page("https://www.indeed.com/cmp/x", "x")
    assert f._BROWSER_EXITS.current()[0] != first                       # spent: rotated alone
    assert len(f._BROWSER_EXITS.current()) == len(set(f._BROWSER_EXITS.current()))   # the others untouched, all distinct
