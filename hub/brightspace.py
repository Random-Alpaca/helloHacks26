"""Brightspace (D2L) adapter: browser-session login (hub.site), then scrape
the "My Courses" list and the Calendar tool's Agenda view for courses and
upcoming due dates.

**[unverified] EVERYTHING IN THIS MODULE IS UNVERIFIED.** UBC does not run
Brightspace - it runs Canvas - so there is no UBC Brightspace instance to
test against, and nobody on this team has ever logged into a live Brightspace
site with this code. This adapter was built from D2L's own public
documentation (community.d2l.com help articles, and the open-source
`@brightspace-ui/core` web-component library that ships in Brightspace's
"Daylight" design system - github.com/BrightspaceUI/core) and publicly
available Brightspace screenshots, never from a real account or a saved
real page. Every selector, regex and date format below is an educated guess
about page structure, not a confirmed fact, unless this docstring is updated
after someone runs it against a real Brightspace tenant. See the Brightspace
row in docs/api-standards.md for exactly which claims are documented facts
vs. guesses, and issue #15's rule 9 (real-endpoint screenshots before merge)
for what "verified" means in this repo - this module does not meet that bar.

D2L Brightspace has no student-facing API (docs/api-standards.md): the only
programmatic access is the Valence API, which needs an admin-issued OAuth2
developer key - the same blocker Workday has. A browser-session scrape (this
module, on `hub.site`'s shared login/session pattern - see hub/prairielearn.py
for the pattern this follows) is the only thing a student could self-serve,
*if* Brightspace's login is even reachable that way, which is unverified: it
depends on how that institution fronts Brightspace SSO, and no institution's
flow has been tried here.

Brightspace is multi-tenant - every institution runs its own subdomain or
custom domain, unlike Canvas's single `canvas.ubc.ca` - so `base` is always
an explicit argument here, never a module-level constant like PrairieLearn's
`BASE`.

Documented facts (cited in docs/api-standards.md's Brightspace row):
- Course URLs use an "Org Unit Number": `/d2l/home/<orgUnitId>` for a
  course's homepage, `/d2l/le/content/<orgUnitId>/Home` for its Content tool.
- The course homepage's Calendar widget shows up to 14 upcoming events/due
  dates, with a "Go to Calendar" link to the full Calendar tool.
- The full Calendar tool has an Agenda view that groups events by Date,
  Course or Category.
- Modern Brightspace UI is built from D2L's own open-source
  `@brightspace-ui/core` Lit web components (`d2l-list`, `d2l-list-item`,
  etc.), so list-shaped tools like the Agenda view are very likely assembled
  from those - but that is an inference, not a citation for this exact page.

Everything else - the precise HTML/DOM these selectors target, the course
tile's title format, the due-date text format, and the timezone the Calendar
displays in - is [unverified]: a plausible guess, not a confirmed page.

Try it (will fail without a real Brightspace instance and login):
  uv run python -m hub.brightspace <base-url>
"""
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from hub import site
from hub.models import Course, Item, category_for

SITE = "brightspace"

# [unverified] Guessed "My Courses" tile title format: "<code> <section>
# (<term>): <title>", e.g. "CPSC 121 101 (2026W1): Models of Computation".
# Modelled on the "code section term: title" shape hub/prairielearn.py
# already parses for a different LMS - not a confirmed Brightspace format.
COURSE_TITLE = re.compile(r"([A-Z]+ ?\d+\w*)\s+(\S+)\s+\((\S+)\):\s*(.+)")

# [unverified] Guessed date-text format for the Calendar Agenda view, based on
# publicly available Brightspace screenshots, e.g. "Sep 27, 2026 11:59 PM".
DATE_RE = re.compile(r"([A-Za-z]{3,9})\s+(\d{1,2}),\s+(\d{4})\s+(\d{1,2}):(\d{2})\s*(AM|PM)")

# [unverified] Guessed mapping from whatever labels the Agenda view's event
# icon/tool name to our `kind`. D2L's own tool names (Dropbox, Quizzes,
# Discussions, Content) are documented; which one each Agenda entry shows,
# and under what attribute/class, is not.
KIND_FOR_LABEL = {
    "assignment": "assignment",
    "dropbox": "assignment",
    "quiz": "quiz",
    "quizzes": "quiz",
    "exam": "exam",
    "discussion": "assignment",
    "discussions": "assignment",
    "content": "reading",
}

# [unverified] Brightspace shows dates in the student's own profile timezone;
# we've found no documentation saying the Agenda view's text carries a zone
# abbreviation the way PrairieLearn's popover does. Same shortcut
# docs/design.md already takes for other providers: default to Pacific time
# and say so loudly, rather than silently mixing naive/aware datetimes.
# ponytail: fixed PDT offset, not zoneinfo - swap for a real zone once
# someone can confirm what the Agenda view actually sends.
_DEFAULT_TZ = timezone(timedelta(hours=-7))


def login(base):
    """Open a visible browser at `base`; the student signs in through
    whatever SSO that institution fronts Brightspace with; save the session.
    [unverified]: never tried against a real Brightspace login page, so the
    "logged in = back on `base` past /login" check hub.site.login makes may
    not hold for Brightspace's actual redirect chain."""
    site.login(SITE, base)


def _get_soup(req, base, path):
    r = req.get(f"{base}{path}")
    if r.status == 401:
        raise site.NotLoggedIn
    if not r.ok:
        raise RuntimeError(f"{path} -> {r.status}")
    return BeautifulSoup(r.text(), "html.parser")


def to_course(tile_text):
    """[unverified] Parse one "My Courses" tile's visible text into a Course.
    Falls back to the raw text as `code` if the guessed format doesn't match
    (same defensive shape as hub/prairielearn.py's to_course - never crash on
    an unexpected title, just keep something useful)."""
    text = tile_text.strip()
    m = COURSE_TITLE.match(text)
    if not m:
        return Course(code=text, section="", term="", title=text)
    code, section, term, title = m.groups()
    return Course(code=code, section=section, term=term, title=title)


# [unverified] Guessed Agenda "group by Course" heading format: just
# "<code> <section>" (no term/title), e.g. "CPSC 121 101".
HEADING_CODE = re.compile(r"([A-Z]+ ?\d+\w*)\s*(\S*)")


def _code_from_heading(heading_text):
    """[unverified] The Agenda view's "group by Course" heading is guessed to
    show only "<code> <section>", not the full tile title."""
    text = heading_text.strip()
    m = HEADING_CODE.match(text)
    if not m:
        return text
    code, section = m.groups()
    return f"{code} {section}".strip()


def _parse_due(date_text):
    """[unverified] see DATE_RE and _DEFAULT_TZ above."""
    m = DATE_RE.search(date_text or "")
    if not m:
        return None
    month, day, year, hour, minute, ampm = m.groups()
    hour = int(hour) % 12 + (12 if ampm.upper() == "PM" else 0)
    try:
        naive = datetime.strptime(f"{month} {day} {year} {hour:02d}:{minute}", "%b %d %Y %H:%M")
    except ValueError:
        return None
    return naive.replace(tzinfo=_DEFAULT_TZ)


def to_item(entry, course_code):
    """[unverified] Parse one guessed Calendar Agenda list-item into an Item.
    `entry` is the list-item's own soup fragment; `course_code` comes from
    the "group by Course" heading above it (see _run/_agenda_items)."""
    link = entry.select_one("a")
    date_el = entry.select_one("time, .d2l-body-small, .d2l-body-compact")
    kind_el = entry.select_one("[data-kind]")
    kind = KIND_FOR_LABEL.get((kind_el["data-kind"] if kind_el else "").strip().lower(), "assignment")
    return Item(
        course=course_code,
        category=category_for(kind),
        kind=kind,
        title=link.get_text(strip=True) if link else entry.get_text(strip=True),
        due=_parse_due(date_el.get_text(strip=True)) if date_el else None,
        url=link["href"] if link and link.has_attr("href") else "",
        source="brightspace",
    )


def _courses(soup):
    """[unverified] "My Courses" tiles: any link to a course homepage
    (`/d2l/home/<orgUnitId>`, the one documented URL shape - see module
    docstring)."""
    out = []
    for a in soup.select("a[href^='/d2l/home/']"):
        org_unit_id = a["href"].rstrip("/").rsplit("/", 1)[-1]
        if org_unit_id.isdigit():
            out.append(to_course(a.get_text(strip=True)))
    return out


def _agenda_items(soup):
    """[unverified] Walk the Agenda view's "group by Course" headings and the
    list-items under each, same "heading row, then item rows" shape
    hub/prairielearn.py's assessments table uses for its own group headings."""
    items, course_code = [], ""
    for el in soup.select("[data-brightspace-heading], .d2l-list-item"):
        if el.has_attr("data-brightspace-heading"):
            course_code = _code_from_heading(el.get_text(strip=True))
        else:
            items.append(to_item(el, course_code))
    return items


def fetch(base):
    """Return (courses, items) for every course on the student's Brightspace
    "My Courses" list, with due dates from the Calendar Agenda view. Opens a
    browser window to log in if there's no saved session.

    [unverified] end to end: no real Brightspace instance has ever answered
    these requests. A login failure, an unrecognised page, or any exception
    while parsing returns ([], []) rather than crashing the dashboard
    (AGENTS.md "handle failure without crashing the dashboard")."""
    try:
        return site.fetch_with_session(SITE, base, lambda req: _run(req, base))
    except Exception:
        return [], []


def _run(req, base):
    course_soup = _get_soup(req, base, "/d2l/home")
    courses = _courses(course_soup)

    agenda_soup = _get_soup(req, base, "/d2l/le/calendar/agenda")
    items = _agenda_items(agenda_soup)
    return courses, items


if __name__ == "__main__":
    import sys

    from hub import db

    if len(sys.argv) < 2:
        print("usage: uv run python -m hub.brightspace <base-url>")
        raise SystemExit(1)
    courses, items = fetch(sys.argv[1])
    db.save(db.connect(), courses, items)
    for c in courses:
        print(f"{c.code:10} {c.term:10} {c.title}")
    print()
    for i in sorted(items, key=lambda i: (i.due is None, i.due or datetime.max.replace(tzinfo=timezone.utc))):
        print(f"{i.due:%a %b %d %H:%M}" if i.due else " " * 16, f"{i.category:9} {i.kind:12} {i.course:10} {i.title}")
