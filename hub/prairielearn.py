"""PrairieLearn adapter: browser-session login (hub.site), then scrape each
enrolled course's Assessments page for tasks/deadlines. No student-facing
API exists (docs/api-standards.md), so this reads the same HTML a student
sees, same as Canvas's browser-login path reads its JSON.

PrairieLearn is open-source and self-hostable by any department or
instructor, not just one deployment per school - a real student's MECH 260
assessments turned out to live on UBC Okanagan's own instance
(prairielearn.ok.ubc.ca), not the shared PrairieLearn SaaS
(us.prairielearn.com) their other courses used, and a search for "known UBC
PrairieLearn domains" turned up a *second*, independent UBC Okanagan
instance (pl.autoed.ok.ubc.ca, a single course's own AutoER tool) - so a
hardcoded list can never be complete. `campus` accepts either a known short
key (CAMPUSES) or a student-pasted "https://..." URL directly - see
resolve_campus(). Same open-source PrairieLearn codebase either way, so the
same scraping logic works against any of them - only the base URL and the
login session differ. Each campus gets its own saved session and its own
`source` value, so items from one never collide with another's.

Verified against a real UBC Vancouver course (CPSC 317, 2026 Winter Term 1).
# ponytail: prairielearn_ok, and any custom domain a student pastes in,
# haven't been verified against a real login - assumed identical markup
# since it's the same PrairieLearn codebase. Flag here if a real login
# shows different HTML.

Two real limitations, not guessed:
- PrairieLearn has no single "due date" - each assessment has a multi-tier
  credit schedule (100% until X, 70% until Y, ...). We take the end of the
  100%-credit tier as `due`, same meaning as "due date" for a student.
- An assessment PrairieLearn hasn't opened yet shows only "Available <time>,
  <weekday>, <month> <day>" (no year, no tier table) - not enough to build an
  exact datetime. Those come back with `due=None` rather than a guess.

Try it:  uv run python -m hub.prairielearn
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from hub import site
from hub.models import Course, Item, category_for

CAMPUSES = {
    "prairielearn": "https://us.prairielearn.com",
    "prairielearn_ok": "https://prairielearn.ok.ubc.ca",
}
DEFAULT_CAMPUS = "prairielearn"


def resolve_campus(campus):
    """A known short key resolves from CAMPUSES; anything else is treated as
    a student-pasted PrairieLearn URL for an instance we don't have listed
    (any department can self-host one - see module docstring). Returns
    (campus_key, base_url); campus_key becomes both the saved-session
    filename (hub.site.state_path) and the item source, so for a custom URL
    it's the bare hostname, not the full URL (filesystem/identity-safe,
    still stable across reconnects to the same instance).

    Rejects anything that isn't a real https:// URL outright - this opens a
    real login browser window at whatever's returned, so a typo or a
    non-URL string must fail loudly here rather than reach Playwright."""
    if campus in CAMPUSES:
        return campus, CAMPUSES[campus]
    parsed = urlparse(campus)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"not a valid https:// PrairieLearn URL: {campus!r}")
    return parsed.netloc, f"https://{parsed.netloc}"

# UBC courses only ever show Pacific time. Fixed offsets, not zoneinfo/pytz:
# good enough while every course we've seen is UBC; add zones if that changes.
TZ_OFFSET = {"PST": -8, "PDT": -7}

# PrairieLearn groups assessments under headings an instructor names freely
# ("Programming Assignments", "Tutorial", ...); these are the ones we've seen
# that mean something other than a plain task. Unlisted -> "assignment".
KIND_FOR_GROUP = {
    "practice for quizzes": "quiz",
    "quizzes": "quiz",
    "formal quizzes": "exam",
    "formal quizzes (repeated for practice)": "exam",
    "exams": "exam",
}

COURSE_TITLE = re.compile(r"([A-Z]+ ?\d+\w*):\s*(.+),\s*(\d{4} \w+ Term \d+)")


def login(campus=DEFAULT_CAMPUS):
    """Open a visible browser; the student signs in (UBC CWL); we save the session."""
    key, base = resolve_campus(campus)
    site.login(key, base)


def _get_soup(req, path, base):
    r = req.get(f"{base}{path}")
    if r.status == 401:
        raise site.NotLoggedIn
    if not r.ok:
        raise RuntimeError(f"{path} -> {r.status}")
    return BeautifulSoup(r.text(), "html.parser")


def to_course(ci_id, title):
    m = COURSE_TITLE.match(title)
    if not m:  # ponytail: title format changed/unexpected - keep the raw text rather than crash
        return Course(code=title, section="", term="", title=title)
    code, name, term = m.groups()
    return Course(code=code, section="", term=term, title=name)


def due_from_popover(popover_html):
    """The access-details popover's first row (100% credit) -> its end time,
    timezone-aware (same as Canvas's due dates - never mix naive and aware
    datetimes in the shared model). None if there's no popover yet (assessment
    not open, see module docstring)."""
    if not popover_html:
        return None
    rows = BeautifulSoup(popover_html, "html.parser").select("tr")[1:]  # skip Credit/Start/End header
    if not rows:
        return None
    end = rows[0].select("td")[2].get_text(strip=True)  # "2026-09-27 23:59:59 (PDT)" or "—"
    m = re.match(r"(.+) \(([A-Z]+)\)$", end)
    if not m:
        return None
    dt_str, tz = m.groups()
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone(timedelta(hours=TZ_OFFSET.get(tz, 0))))


def to_item(row, course_code, group, campus_key, base):
    cells = row.select("td")
    link = cells[1].find("a")
    popover = cells[2].find("button")
    kind = KIND_FOR_GROUP.get(group.strip().lower(), "assignment")
    return Item(
        course=course_code,
        category=category_for(kind),
        kind=kind,
        title=cells[1].get_text(strip=True),
        due=due_from_popover(popover["data-bs-content"]) if popover else None,
        url=f"{base}{link['href']}" if link else "",
        source=campus_key,
    )


def _course_instances(req, base):
    """[(id, display title)] for every course on the student's home page."""
    soup = _get_soup(req, "/", base)
    return [(a["href"].rsplit("/", 1)[1], a.get_text(strip=True))
            for a in soup.select("a[href^='/pl/course_instance/']")
            if a["href"].rstrip("/").count("/") == 3]


def _assessments(req, ci_id, course_code, campus_key, base):
    soup = _get_soup(req, f"/pl/course_instance/{ci_id}/assessments", base)
    items, group = [], ""
    for row in soup.select("table tbody tr"):
        heading = row.find("th")
        if heading:
            group = heading.get_text(strip=True)
        else:
            items.append(to_item(row, course_code, group, campus_key, base))
    return items


def fetch(campus=DEFAULT_CAMPUS):
    """Return (courses, items) for every course on the student's PrairieLearn
    home page, for the given campus (a known CAMPUSES key, or a full
    https://... URL - see resolve_campus()). Opens a browser window to log
    in if there's no saved session for that campus."""
    key, base = resolve_campus(campus)
    return site.fetch_with_session(key, base, lambda req: _run(req, key, base))


def _run(req, campus_key, base):
    courses, items = [], []
    for ci_id, title in _course_instances(req, base):
        course = to_course(ci_id, title)
        courses.append(course)
        items += _assessments(req, ci_id, course.code, campus_key, base)
    return courses, items


if __name__ == "__main__":
    import sys

    from hub import db

    campus = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CAMPUS
    courses, items = fetch(campus)
    db.save(db.connect(), courses, items)
    for c in courses:
        print(f"{c.code:10} {c.term:20} {c.title}")
    print()
    for i in sorted(items, key=lambda i: (i.due is None, i.due or datetime.max)):
        print(f"{i.due:%a %b %d %H:%M}" if i.due else " " * 16, f"{i.category:9} {i.kind:12} {i.course:10} {i.title}")
