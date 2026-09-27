"""WeBWorK adapter: browser-session login (hub.site), then scrape a course's
problem-set list page for tasks/deadlines.

**[unverified]** Unlike hub/prairielearn.py, nobody on the team has pulled up
a real, live WeBWorK course to confirm this page's markup. WeBWorK is open
source and its problem-set-list template (`ProblemSets.pm`) is public, so the
table shape below (a set name link, an open date, a due date, and sometimes a
reduced-scoring date and a grade) matches the documented/screenshotted
structure closely-watched WeBWorK deployments show - it is NOT scraped from a
live instance. Treat every selector here as a best guess until a human with a
real WeBWorK account (UBC or otherwise) checks it against a live course and
updates this docstring.

Why this exists (see issue #23): at UBC, WeBWorK sets are usually embedded in
Canvas as an "External Tool" assignment, so hub/canvas.py likely already
lists them. But grades sync to Canvas roughly daily and **due dates don't
sync at all** - the instructor types the Canvas due date in by hand, so it
can drift from the real WeBWorK due date. This adapter exists for two cases:
1. Correcting that drift: fetch WeBWorK's own due date and compare/override
   the Canvas one for the same set.
2. Schools/courses that run WeBWorK standalone, with no LMS in front of it
   at all (this project's stated "other schools too" mission, per AGENTS.md).

Login caveat: hub.site.login() waits for the browser to land back on `base`
with "/login" no longer in the URL - true for Canvas and PrairieLearn because
UBC fronts both with the same CWL redirect. WeBWorK's *own* built-in login
(used by schools that don't front it with an SSO) instead renders a login
form directly on `base` and never navigates away on failure, and stays on
`base` on success too - so the redirect-based wait should still resolve, but
this is unverified against a real standalone WeBWorK login page. If a school
fronts WeBWorK with its own SSO (UBC: CWL), that should behave like Canvas.

Try it:  uv run python -m hub.webwork <course-url>
"""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from hub import site
from hub.models import Course, Item, category_for

SITE = "webwork"

# Common North American zone abbreviations WeBWorK's date strings show.
# Fixed offsets, not zoneinfo/pytz - same shortcut hub/prairielearn.py takes,
# for the same reason: good enough until a course in a different zone shows
# up, and cheap to extend then.
TZ_OFFSET = {
    "PST": -8, "PDT": -7,
    "MST": -7, "MDT": -6,
    "CST": -6, "CDT": -5,
    "EST": -5, "EDT": -4,
}

# WeBWorK's date strings look like "09/14/2026 at 11:59pm PDT" (documented
# format; [unverified] against a live page - see module docstring).
DATE_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})/(\d{4})\s+at\s+(\d{1,2}):(\d{2})\s*(am|pm)\s*([A-Z]{2,4})?",
    re.IGNORECASE,
)


def login(base):
    """Open a visible browser at the course's WeBWorK URL; the student signs
    in; we save the session. See the module docstring's login caveat."""
    site.login(SITE, base)


def _get_soup(req, url):
    r = req.get(url)
    if r.status == 401:
        raise site.NotLoggedIn
    if not r.ok:
        raise RuntimeError(f"{url} -> {r.status}")
    return BeautifulSoup(r.text(), "html.parser")


def due_from_text(text):
    """Parse a WeBWorK date string ("09/14/2026 at 11:59pm PDT") into a
    tz-aware datetime. None if the text has no such date (e.g. "n/a",
    a blank cell, or a set that isn't open yet)."""
    if not text:
        return None
    m = DATE_RE.search(text)
    if not m:
        return None
    month, day, year, hour, minute, ampm, tz = m.groups()
    hour = int(hour) % 12
    if ampm.lower() == "pm":
        hour += 12
    dt = datetime(int(year), int(month), int(day), hour, int(minute))
    return dt.replace(tzinfo=timezone(timedelta(hours=TZ_OFFSET.get((tz or "").upper(), 0))))


def _is_complete(score_text):
    """WeBWorK shows a set's score as a percentage once it's graded. Treat an
    exact "100%" as done and anything else (partial score, "N/A", blank) as
    unknown rather than guessing "not done" - a low score might still be a
    student who is still working on it.
    # ponytail: crude heuristic, not a real completion signal (WeBWorK has no
    # simple "submitted" flag on this page as far as we've seen documented).
    # Upgrade if a live page shows a clearer per-set status."""
    if score_text and score_text.strip() == "100%":
        return True
    return None


def to_item(row, course_code, base=""):
    """One <tr> of the problem-sets table -> an Item. Expects a link cell
    (set name + url) and a due-date cell; a score cell is optional. `base`
    resolves a relative href into an absolute URL; pass "" in tests where
    the exact host doesn't matter."""
    cells = row.select("td")
    date_cells = [c for c in cells if due_from_text(c.get_text(" ", strip=True))]
    # The set list shows an open date *and* a due date (and sometimes a
    # reduced-scoring date) side by side - all match the same date pattern.
    # We want the due date specifically. Per the documented column order
    # (open, [reduced-scoring,] due), that's the last date-shaped cell before
    # any trailing score column - so take the last match, not the first.
    due_cell = date_cells[-1] if date_cells else None
    link = row.find("a")
    score_cell = next((c for c in cells if c.get_text(strip=True).endswith("%")), None)
    if link:
        title = link.get_text(strip=True)
    elif cells:
        title = cells[0].get_text(strip=True)
    else:  # a header row (<th> only, no <td>) - degrade rather than crash
        title = row.get_text(strip=True)
    return Item(
        course=course_code,
        category=category_for("problemset"),
        kind="problemset",
        title=title,
        due=due_from_text(due_cell.get_text(" ", strip=True)) if due_cell else None,
        url=urljoin(base, link["href"]) if link and link.get("href") else "",
        source=SITE,
        done=_is_complete(score_cell.get_text(strip=True)) if score_cell else None,
    )


def _problem_sets(req, base, course_code):
    soup = _get_soup(req, base)
    items = []
    # WeBWorK's set list is documented as a single <table> of one row per
    # set; skip header rows (no link in the row) rather than assuming a
    # fixed row count, same defensive spirit as prairielearn's group-heading
    # skip.
    for row in soup.select("table tr"):
        if row.find("a"):
            items.append(to_item(row, course_code, base))
    return items


def fetch(base, course_code):
    """Return items for the WeBWorK course at `base` (e.g.
    "https://webwork.example.edu/webwork2/math101/"). `course_code` is
    supplied by the caller (there's no student-facing course-catalogue join
    key on this page as far as we've seen documented) so items can be
    matched against the same course from Canvas/Workday. Opens a browser
    window to log in if there's no saved session."""
    return site.fetch_with_session(SITE, base, lambda req: _problem_sets(req, base, course_code))


if __name__ == "__main__":
    import sys

    from hub import db

    if len(sys.argv) < 3:
        print("usage: uv run python -m hub.webwork <course-url> <course-code>")
        raise SystemExit(1)
    course_url, course_code = sys.argv[1], sys.argv[2]
    items = fetch(course_url, course_code)
    db.save(db.connect(), [Course(code=course_code, section="", term="", title=course_code)], items)
    for i in sorted(items, key=lambda i: (i.due is None, i.due or datetime.max)):
        print(f"{i.due:%a %b %d %H:%M}" if i.due else " " * 16, f"{i.category:9} {i.kind:12} {i.course:10} {i.title}")
