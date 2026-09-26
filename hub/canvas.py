"""Canvas adapter without API tokens.

The student logs in to canvas.ubc.ca themselves (CWL + Duo) in a real browser
window. We save that browser session and call the same /api/v1 JSON endpoints
Canvas's own web pages use. We never see or store the CWL password.

Try it:  uv run python -m hub.canvas
"""
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright
from requests.utils import parse_header_links

from hub.models import Course, Item

BASE = "https://canvas.ubc.ca"
# Session cookies are as good as a password: keep them outside the repo, owner-only.
STATE = Path.home() / ".ubc-hub" / "canvas-state.json"
KINDS = {"announcement": "announcement", "calendar_event": "event"}  # everything else is work to do


class NotLoggedIn(Exception):
    pass


def parse_json(text):
    # Canvas prefixes cookie-authenticated JSON with while(1); to block JSON hijacking.
    return json.loads(text.removeprefix("while(1);"))


def next_link(link_header):
    return next((l["url"] for l in parse_header_links(link_header or "") if l.get("rel") == "next"), None)


def to_course(c):
    enr = next(iter(c.get("enrollments") or []), {})
    return Course(
        code=c.get("course_code", ""),
        section="",  # ponytail: Canvas codes aren't consistent enough to split; match on Workday's side
        term=(c.get("term") or {}).get("name", ""),
        title=c.get("name", ""),
        grade=enr.get("computed_current_score"),
    )


def to_item(p, course_codes):
    due = p.get("plannable_date")
    return Item(
        course=course_codes.get(p.get("course_id"), p.get("context_name", "")),
        kind=KINDS.get(p.get("plannable_type"), "assignment"),
        title=(p.get("plannable") or {}).get("title", ""),
        due=datetime.fromisoformat(due) if due else None,
        url=BASE + p.get("html_url", ""),
        source="canvas",
    )


def _get_all(req, path, params):
    url, out = f"{BASE}/api/v1/{path}?{urlencode(params, doseq=True)}", []
    while url:
        for attempt in range(5):
            r = req.get(url)
            if r.status != 429:
                break
            time.sleep(2**attempt)  # throttled: back off
        if r.status == 401:
            raise NotLoggedIn
        if not r.ok:
            raise RuntimeError(f"Canvas {r.status} on {path}")
        out += parse_json(r.text())
        url = next_link(r.headers.get("link"))
    return out


def login():
    """Open a visible browser; the student signs in; we save the session."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(BASE)
        # Done once we're back on Canvas past the CWL/Duo pages. 5 minutes to finish Duo.
        page.wait_for_url(lambda u: u.startswith(BASE) and "/login" not in u, timeout=300_000)
        STATE.parent.mkdir(mode=0o700, exist_ok=True)
        page.context.storage_state(path=STATE)
        STATE.chmod(0o600)
        browser.close()


def fetch(start=None, end=None):
    """Return (courses, items) for start..end (default: today + 7 days). Logs in if needed."""
    start = start or date.today()
    end = end or start + timedelta(days=7)
    if not STATE.exists():
        login()
    try:
        return _fetch(start, end)
    except NotLoggedIn:  # session expired
        login()
        return _fetch(start, end)


def _fetch(start, end):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(storage_state=STATE)
        try:
            raw = _get_all(ctx.request, "courses", {
                "include[]": ["total_scores", "term"], "enrollment_state": "active", "per_page": 100})
            courses = [to_course(c) for c in raw]
            codes = {c["id"]: c.get("course_code", "") for c in raw}
            plan = _get_all(ctx.request, "planner/items", {
                "start_date": start.isoformat(), "end_date": end.isoformat(), "per_page": 100})
            return courses, [to_item(p, codes) for p in plan]
        finally:
            browser.close()


if __name__ == "__main__":
    courses, items = fetch()
    for c in courses:
        print(f"{c.code:30} {c.grade if c.grade is not None else '-':>6}  {c.title}")
    print()
    for i in sorted(items, key=lambda i: (i.due is None, i.due or 0)):
        print(f"{i.due:%a %b %d %H:%M}" if i.due else " " * 16, f"{i.kind:12} {i.course:20} {i.title}")
