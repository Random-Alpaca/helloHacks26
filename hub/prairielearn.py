"""PrairieLearn adapter: browser-session login (hub.site), then scrape each
enrolled course's Assessments page for tasks/deadlines. No student-facing
API exists (docs/api-standards.md), so this reads the same HTML a student
sees, same as Canvas's browser-login path reads its JSON.

Verified against a real UBC course (CPSC 317, 2026 Winter Term 1). Two real
limitations, not guessed:
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
from urllib.parse import quote

from bs4 import BeautifulSoup

from hub import site
from hub.models import Course, Item, category_for

BASE = "https://us.prairielearn.com"
SITE = "prairielearn"

# UBC courses only ever show Pacific time. Fixed offsets, not zoneinfo/pytz:
# good enough while every course we've seen is UBC; add zones if that changes.
# "MST" included for BC's 2027-01-06 permanent-DST tzdata change (see
# tests/test_db.py): once BC stops changing clocks, tzdata names the resulting
# fixed UTC-7 offset "MST" (it coincides with Mountain Standard Time), even
# though it's still what PrairieLearn shows as "Vancouver time".
TZ_OFFSET = {"PST": -8, "PDT": -7, "MST": -7}

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


def login():
    """Open a visible browser; the student signs in (UBC CWL); we save the session."""
    site.login(SITE, BASE)


def _get_soup(req, path):
    r = req.get(f"{BASE}{path}")
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
    if tz not in TZ_OFFSET:
        # Silently treating an unrecognized abbreviation as UTC used to be a
        # 7h-off bug waiting to happen (#15) - fail loud instead.
        raise ValueError(f"unrecognized PrairieLearn timezone abbreviation: {tz!r}")
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone(timedelta(hours=TZ_OFFSET[tz])))


def to_item(row, course_code, group, ci_id):
    cells = row.select("td")
    link = cells[1].find("a")
    popover = cells[2].find("button")
    kind = KIND_FOR_GROUP.get(group.strip().lower(), "assignment")
    title = cells[1].get_text(strip=True)
    # An assessment PrairieLearn hasn't opened yet has no link (module
    # docstring), so url="" used to be its identity - every unreleased
    # assessment in every course collapsed onto one hub.db row (#15). Fall
    # back to the assessments page plus the title, unique enough within a
    # course and stable across re-fetches until the assessment actually opens.
    url = f"{BASE}{link['href']}" if link else f"{BASE}/pl/course_instance/{ci_id}/assessments#{quote(title)}"
    return Item(
        course=course_code,
        category=category_for(kind),
        kind=kind,
        title=title,
        due=due_from_popover(popover["data-bs-content"]) if popover else None,
        url=url,
        source="prairielearn",
    )


_CI_LINK = re.compile(r"^/pl/course_instance/(\d+)(?:/instructor)?/?$")


def _course_instances(req):
    """[(id, display title)] for every course on the student's home page.

    Matches both the student link (.../course_instance/<id>) and the
    instructor one (.../course_instance/<id>/instructor) - TAs/instructors
    used to see zero courses because only the student shape matched (#15).
    # ponytail: this still reads the student Assessments page for everyone
    (_assessments below), which may not be right for an instructor-only
    account - untested without a real TA login. Revisit if that's wrong."""
    soup, seen, out = _get_soup(req, "/"), set(), []
    for a in soup.select("a[href^='/pl/course_instance/']"):
        m = _CI_LINK.match(a["href"])
        if not m or m[1] in seen:
            continue
        seen.add(m[1])
        out.append((m[1], a.get_text(strip=True)))
    return out


def _assessments(req, ci_id, course_code):
    soup = _get_soup(req, f"/pl/course_instance/{ci_id}/assessments")
    items, group = [], ""
    for row in soup.select("table tbody tr"):
        heading = row.find("th")
        if heading:
            group = heading.get_text(strip=True)
        else:
            items.append(to_item(row, course_code, group, ci_id))
    return items


def fetch():
    """Return (courses, items) for every course on the student's PrairieLearn
    home page. Opens a browser window to log in if there's no saved session."""
    return site.fetch_with_session(SITE, BASE, _run)


def _run(req):
    courses, items = [], []
    for ci_id, title in _course_instances(req):
        course = to_course(ci_id, title)
        courses.append(course)
        items += _assessments(req, ci_id, course.code)
    return courses, items


if __name__ == "__main__":
    from hub import db

    courses, items = fetch()
    db.save(db.connect(), courses, items)
    for c in courses:
        print(f"{c.code:10} {c.term:20} {c.title}")
    print()
    for i in sorted(items, key=lambda i: (i.due is None, i.due or datetime.max)):
        print(f"{i.due:%a %b %d %H:%M}" if i.due else " " * 16, f"{i.category:9} {i.kind:12} {i.course:10} {i.title}")
