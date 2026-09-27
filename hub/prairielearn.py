"""PrairieLearn adapter: browser-session login (hub.site), then scrape each
enrolled course's Assessments page for tasks/deadlines. No student-facing
API exists (docs/api-standards.md), so this reads the same HTML a student
sees, same as Canvas's browser-login path reads its JSON.

Two UBC PrairieLearn deployments exist - the shared PrairieLearn SaaS most
UBC Vancouver courses use (us.prairielearn.com), and UBC Okanagan's own
self-hosted instance (prairielearn.ok.ubc.ca) for courses taught there (e.g.
a student found their real MECH 260 assessments live there, not on the
Vancouver instance). Same open-source PrairieLearn codebase either way, so
the same scraping logic works against both - only the base URL and the
login session differ, so a `campus` key threads through instead of a
hardcoded site/base pair. Each campus gets its own saved session and its
own `source` value, so items from one never collide with the other's.

Verified against a real UBC Vancouver course (CPSC 317, 2026 Winter Term 1).
# ponytail: prairielearn_ok hasn't been verified against a real login yet -
# assumed identical markup since it's the same PrairieLearn codebase. Flag
# here (and adjust CAMPUSES/parsing as needed) if a real UBC-O login shows
# different HTML.

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

from bs4 import BeautifulSoup

from hub import site
from hub.models import Course, Item, category_for

CAMPUSES = {
    "prairielearn": "https://us.prairielearn.com",
    "prairielearn_ok": "https://prairielearn.ok.ubc.ca",
}
DEFAULT_CAMPUS = "prairielearn"

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
    site.login(campus, CAMPUSES[campus])


def _get_soup(req, path, campus):
    r = req.get(f"{CAMPUSES[campus]}{path}")
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


def to_item(row, course_code, group, campus):
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
        url=f"{CAMPUSES[campus]}{link['href']}" if link else "",
        source=campus,
    )


def _course_instances(req, campus):
    """[(id, display title)] for every course on the student's home page."""
    soup = _get_soup(req, "/", campus)
    return [(a["href"].rsplit("/", 1)[1], a.get_text(strip=True))
            for a in soup.select("a[href^='/pl/course_instance/']")
            if a["href"].rstrip("/").count("/") == 3]


def _assessments(req, ci_id, course_code, campus):
    soup = _get_soup(req, f"/pl/course_instance/{ci_id}/assessments", campus)
    items, group = [], ""
    for row in soup.select("table tbody tr"):
        heading = row.find("th")
        if heading:
            group = heading.get_text(strip=True)
        else:
            items.append(to_item(row, course_code, group, campus))
    return items


def fetch(campus=DEFAULT_CAMPUS):
    """Return (courses, items) for every course on the student's PrairieLearn
    home page, for the given campus. Opens a browser window to log in if
    there's no saved session for that campus."""
    return site.fetch_with_session(campus, CAMPUSES[campus], lambda req: _run(req, campus))


def _run(req, campus):
    courses, items = [], []
    for ci_id, title in _course_instances(req, campus):
        course = to_course(ci_id, title)
        courses.append(course)
        items += _assessments(req, ci_id, course.code, campus)
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
