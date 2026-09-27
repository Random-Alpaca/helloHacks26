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

from bs4 import BeautifulSoup

from hub import site
from hub.models import Course, Item, category_for

BASE = "https://us.prairielearn.com"
SITE = "prairielearn"

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
    return datetime.fromisoformat(dt_str).replace(tzinfo=timezone(timedelta(hours=TZ_OFFSET.get(tz, 0))))


_SCORE_RE = re.compile(r"([\d.]+)\s*%")


def done_from_score(cells):
    """PrairieLearn has no submitted/graded flag of its own on this page -
    the 4th column shows a percentage ("100%") once attempted, or a status
    like "Not started"/"Not yet released" otherwise. A 100% score is one
    heuristic for "nothing left to do here" (a lower score is still
    improvable up until the assessment closes - see done_from_credit for the
    other case, a closed assessment whose score never reached 100%)."""
    if len(cells) < 4:
        return None
    m = _SCORE_RE.search(cells[3].get_text(strip=True))
    return m is not None and float(m.group(1)) >= 100


def done_from_credit(cells):
    """Once an assessment's whole credit schedule has expired, the Available
    Credit column (3rd) shows nothing at all - no popover, no "Available
    <time>" notice - since there's nothing left that could still change the
    score. Verified against a real UBC course: several closed assessments
    show this with a score well under 100% (e.g. 66%, 80%, 85%), which
    done_from_score alone would miss. A not-yet-open assessment always shows
    an "Available <time>" message instead, so this never collides with that
    case."""
    if len(cells) < 3:
        return False
    credit_cell = cells[2]
    return credit_cell.find("button") is None and credit_cell.get_text(strip=True) == ""


def to_item(row, course_code, group):
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
        url=f"{BASE}{link['href']}" if link else "",
        source="prairielearn",
        done=bool(done_from_score(cells)) or done_from_credit(cells),
    )


def _course_instances(req):
    """[(id, display title)] for every course on the student's home page."""
    soup = _get_soup(req, "/")
    return [(a["href"].rsplit("/", 1)[1], a.get_text(strip=True))
            for a in soup.select("a[href^='/pl/course_instance/']")
            if a["href"].rstrip("/").count("/") == 3]


def _assessments(req, ci_id, course_code):
    soup = _get_soup(req, f"/pl/course_instance/{ci_id}/assessments")
    items, group = [], ""
    for row in soup.select("table tbody tr"):
        heading = row.find("th")
        if heading:
            group = heading.get_text(strip=True)
        else:
            items.append(to_item(row, course_code, group))
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
