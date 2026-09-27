"""Zero-click demo: a made-up "Demo Student" run through the real adapters.

The hosted site (web/, Sample mode) has no login and no database, but it
should still show what Hub actually does - so instead of hand-typed sample
rows, demo_rows() replays saved, fake provider captures
(hub/demo_fixtures/) through the same functions a live fetch uses:

- Canvas: canvas._run() over an in-memory transport serving API-shaped JSON
  (courses, planner/items, per-course assignments)
- Canvas calendar feed: ics.parse() over a .ics file
- PrairieLearn: prairielearn._run() over the same transport serving HTML
- Workday: workday.parse_workday_courses() over an .xlsx export
- UBC key dates: key_dates.fetch()

then fuses them the way hub/api.py's /api/upcoming does (logic.dedupe,
status_of, sort_items, api._row_to_dict). No network, browser or database:
the transport below only reads files next to this module.

Fixture dates are stored as offsets ("{{due:+2d@23:59}}" = two days from
today, 23:59 Vancouver time) and rendered into each provider's own date
format at request time, so the demo never goes stale.

Everything in hub/demo_fixtures/ is fake: no real student, instructor or
course content.
"""
import json
import re
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from hub import api, canvas, ics, key_dates, prairielearn, workday
from hub.db import _canonical_code, _canonical_term
from hub.logic import dedupe, sort_items
from hub.models import status_of

FIXTURES = Path(__file__).parent / "demo_fixtures"
VAN = ZoneInfo("America/Vancouver")
TERM = "2026W1"
_DUE = re.compile(r"\{\{due:([+-]\d+)d@(\d{2}):(\d{2})\}\}")


def _when(match, now):
    days, hh, mm = int(match[1]), int(match[2]), int(match[3])
    day = now.astimezone(VAN).date() + timedelta(days=days)
    return datetime.combine(day, time(hh, mm), tzinfo=VAN)


# Each provider's own on-the-wire date format, so its real parser does the parsing.
_FORMATS = {
    "canvas": lambda dt: dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "ics": lambda dt: dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
    "prairielearn": lambda dt: f"{dt:%Y-%m-%d %H:%M:%S} ({dt.tzname()})",
}


def _render(name, fmt, now):
    text = (FIXTURES / name).read_text()
    return _DUE.sub(lambda m: _FORMATS[fmt](_when(m, now)), text)


class _Response:
    def __init__(self, body, status=200):
        self.status, self.ok, self.headers, self._body = status, 200 <= status < 300, {}, body

    def text(self):
        return self._body


# The demo student is on PrairieLearn's default campus - same key/base a
# real hub.prairielearn.fetch() with no argument resolves to.
_PL_KEY, _PL_BASE = prairielearn.resolve_campus(prairielearn.DEFAULT_CAMPUS)


class _FixtureRequest:
    """Stands in for the logged-in browser session hub.site hands an
    adapter's _run(): same .get(url) -> response interface, but every URL is
    answered from hub/demo_fixtures/ instead of the network."""

    def __init__(self, now):
        self.now = now

    def get(self, url):
        parsed = urlparse(url)
        host, path = parsed.hostname, parsed.path.rstrip("/")
        if host == urlparse(canvas.BASE).hostname:
            if path == "/api/v1/courses":
                return _Response(_render("canvas_courses.json", "canvas", self.now))
            if path == "/api/v1/planner/items":
                return _Response(_render("canvas_planner_items.json", "canvas", self.now))
            m = re.fullmatch(r"/api/v1/courses/(\d+)/assignments", path)
            if m:
                by_course = json.loads(_render("canvas_assignments.json", "canvas", self.now))
                return _Response(json.dumps(by_course.get(m[1], [])))
        if host == urlparse(_PL_BASE).hostname:
            if path == "":
                return _Response(_render("prairielearn_home.html", "prairielearn", self.now))
            m = re.fullmatch(r"/pl/course_instance/(\d+)/assessments", path)
            if m and (FIXTURES / f"prairielearn_assessments_{m[1]}.html").exists():
                return _Response(_render(f"prairielearn_assessments_{m[1]}.html", "prairielearn", self.now))
        return _Response("not in the demo fixtures", status=404)


def _gather(now):
    """(courses, items) from every demo provider, straight out of the real
    adapters - nothing fused yet. Canvas's API path and its calendar feed
    both run, as they would for a student who connected both."""
    req = _FixtureRequest(now)
    today = now.astimezone(VAN).date()
    courses, items = [], []
    courses += workday.parse_workday_courses(FIXTURES / "workday_view_my_courses.xlsx", TERM)
    c_courses, c_items = canvas._run(req, today - timedelta(days=120), today + timedelta(days=120))
    courses += c_courses
    items += c_items
    items += ics.parse(_render("canvas_calendar.ics", "ics", now), "canvas")
    p_courses, p_items = prairielearn._run(req, _PL_KEY, _PL_BASE)
    courses += p_courses
    items += p_items
    k_courses, k_items = key_dates.fetch("UBCV", TERM, now=now)
    courses += k_courses
    items += k_items
    return courses, items


def _fuse_courses(courses):
    """One row per canonical course code - the same merge hub.db.save()
    does (#41): shorter title wins, a known grade survives an unknown one.
    # ponytail: mirrors db._course_id() in memory because the demo mustn't
    # open a database; if that merge rule changes, change this with it.
    """
    fused = {}
    for c in courses:
        code, term = _canonical_code(c.code), _canonical_term(c.term)
        row = fused.setdefault(code, {"code": code, "term": term, "title": c.title, "grade": c.grade})
        row["term"] = row["term"] or term
        if len(c.title) < len(row["title"]):
            row["title"] = c.title
        if c.grade is not None:
            row["grade"] = c.grade
    return sorted(fused.values(), key=lambda r: r["code"])


def _row(item):
    """Item -> hub.db.upcoming()'s row shape, course code canonicalised the
    way save() joins it, so api._row_to_dict() serialises it unchanged."""
    return (_canonical_code(item.course), item.category, item.kind, item.title,
            item.due.isoformat() if item.due else None, item.url, item.done, item.source)


def demo_rows(now=None):
    """The whole demo dashboard as JSON-ready data: {"demo": true, "items":
    [...] (ranked, /api/upcoming's shape), "announcements": [...]
    (/api/announcements' shape), "courses": [...] (/api/courses' shape)}."""
    now = now or datetime.now(timezone.utc)
    courses, items = _gather(now)
    # Canonicalise course codes first so dedupe() sees Canvas's
    # "CPSC_110_101_2026W1" and PrairieLearn's "CPSC 110" as one course -
    # hub.db does the same when it joins items to course rows.
    for i in items:
        i.course = _canonical_code(i.course)
    items = dedupe(items)
    # dedupe() keys on (course, title, due); rule 4's (source, url) identity is
    # the other half - the db upsert. Same key, first one seen wins.
    by_identity = {}
    for i in items:
        by_identity.setdefault((i.source, i.url), i)
    rows = [_row(i) for i in by_identity.values()]
    dated = [r for r in rows if r[4] and status_of(api._item_of(r), now) != "done"]
    upcoming = [api._row_to_dict(r, now) for r in sort_items(dated, now)]
    announcements = [api._row_to_dict(r, now) for r in rows if r[4] is None and r[2] == "announcement"]
    return {"demo": True, "items": upcoming, "announcements": announcements, "courses": _fuse_courses(courses)}
