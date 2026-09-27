"""One iCalendar parser for any school's feed (Canvas, Moodle, ...).

Canvas and Moodle both expose a per-student .ics URL (docs/api-standards.md
"Architecture suggestion"). Feed URLs carry a secret, same as a token: never
log or commit one.

Verified against a real self-hosted Canvas (instructure/canvas-lms) feed,
found via #47: every event's URL is the *generic* course calendar page
(.../calendar?include_contexts=course_N), never the item's own page, which
broke two things - kind ("/calendar_events/" in url never matched, so
office hours and everything else came back "assignment"), and identity
(every item in a course collided on the same (source, url), breaking rule
4). UID carries the real signal instead: Canvas's own event-assignment-<id>
/ event-calendar-event-<id> format. The deep link is rebuilt from UID's id
plus the course id already sitting in that same generic URL's query string
- no extra request needed, so the no-auth "paste your feed link" flow still
needs nothing but the feed itself.
"""
import os
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import requests
from icalendar import Calendar

from hub.models import Item, category_for, classify_urgency, status_of

# Canvas puts "[COURSE CODE]" on the end of every event/assignment summary.
# Moodle feeds don't, so course comes back "" there - fine for a first cut.
COURSE_SUFFIX = re.compile(r"\s*\[(.+?)\]\s*$")

# Canvas's own UID shape for a calendar-feed VEVENT.
UID_RE = re.compile(r"^event-(assignment|calendar-event)-(\d+)$")
# The course id sitting in the generic URL every feed item currently ships
# with (.../calendar?include_contexts=course_12345).
COURSE_ID_RE = re.compile(r"course_(\d+)")


def _due(dt):
    """dtstart.dt is a bare `date` for an all-day event (no time component) -
    never a naive datetime here, matching every other adapter's "always
    tz-aware or None" rule. A timed event's dt is already tz-aware (Canvas's
    feed uses UTC "Z" instants), so it passes through unchanged."""
    if isinstance(dt, datetime):
        return dt
    if isinstance(dt, date):
        return datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc)
    return None


def _kind_and_id(uid, url):
    m = UID_RE.match(uid)
    if m:
        kind = "assignment" if m.group(1) == "assignment" else "event"
        return kind, m.group(2)
    # ponytail: UID didn't match the known Canvas shape (a different school's
    # feed, or a format change) - fall back to the old URL guess rather than
    # crash. No item id means no deep link rebuild either (see _deep_link).
    return ("event" if "/calendar_events/" in url else "assignment"), None


def _deep_link(url, kind, item_id):
    """The item's own page, not the generic calendar page every event's URL
    otherwise shares - rebuilt from the course id already in that URL's
    query string plus UID's item id. Falls back to the feed's own (generic,
    but real) URL when either piece is missing, and always includes UID as
    a fragment so (source, url) stays unique per item even then (rule 4)."""
    if item_id is None:
        return url
    course_m = COURSE_ID_RE.search(url)
    if not course_m:
        return f"{url}#{item_id}" if url else ""
    parsed = urlparse(url)
    path = "assignments" if kind == "assignment" else "calendar_events"
    return f"{parsed.scheme}://{parsed.netloc}/courses/{course_m.group(1)}/{path}/{item_id}"


def parse(ics_text, source):
    """.ics text -> list[Item]. `source` tags where it came from, e.g. "canvas"."""
    items = []
    for event in Calendar.from_ical(ics_text).walk("VEVENT"):
        summary = str(event.get("summary", ""))
        m = COURSE_SUFFIX.search(summary)
        dtstart = event.get("dtstart")
        url = str(event.get("url", ""))
        uid = str(event.get("uid", ""))
        kind, item_id = _kind_and_id(uid, url)
        items.append(Item(
            course=m.group(1) if m else "",
            category=category_for(kind),
            kind=kind,
            title=COURSE_SUFFIX.sub("", summary),
            due=_due(dtstart.dt) if dtstart else None,
            url=_deep_link(url, kind, item_id),
            source=source,
        ))
    return items


def fetch(feed_url, source):
    """Feed URL -> list[Item]. Raises requests.HTTPError on a bad/expired URL.
    No host/size guard - only for a feed URL from a trusted context (e.g.
    already known, not freshly typed by a stranger on the internet). A
    student-submitted URL (POST /api/feed) must go through fetch_untrusted()
    instead."""
    r = requests.get(feed_url, timeout=30)
    r.raise_for_status()
    return parse(r.text, source)


# SSRF guard for /api/feed (#47): a student can paste ANY string here, and
# this fetches it server-side (Canvas sends no CORS headers, so the browser
# can't fetch it directly) - so only a known-safe https host may be reached
# this way, never an arbitrary one.
ALLOWED_FEED_HOSTS = ("canvas.ubc.ca",)
ALLOWED_FEED_HOST_SUFFIXES = (".instructure.com",)
MAX_FEED_BYTES = 5_000_000
FEED_TIMEOUT_S = 15


def is_allowed_feed_host(url):
    """True if `url` is a real https:// URL on the allowlist above, or on
    FEED_ORACLE_HOST (an env var, test-only - our self-hosted Canvas for
    live testing; never set this in production)."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return False
    host = parsed.hostname
    oracle_host = os.environ.get("FEED_ORACLE_HOST")
    if oracle_host and host == oracle_host:
        return True
    return host in ALLOWED_FEED_HOSTS or any(host.endswith(s) for s in ALLOWED_FEED_HOST_SUFFIXES)


def fetch_untrusted(url, source):
    """Validate, fetch, parse - the one function both /api/feed
    implementations (hub/api.py for local mode, the Vercel function for the
    hosted site) call, so the host allowlist and size/time limits live in
    exactly one place (rule 1). Never logs `url` - it's a secret, like a
    token. Raises ValueError if the host isn't allowed or the response is
    too large, requests.HTTPError/Timeout on a bad, expired or slow feed."""
    if not is_allowed_feed_host(url):
        raise ValueError("that isn't an allowed Canvas calendar-feed host")
    r = requests.get(url, timeout=FEED_TIMEOUT_S, stream=True)
    r.raise_for_status()
    body = r.raw.read(MAX_FEED_BYTES + 1, decode_content=True)
    if len(body) > MAX_FEED_BYTES:
        raise ValueError("feed response too large")
    return parse(body.decode("utf-8", errors="replace"), source)


def to_dict(item, now):
    """Item -> JSON-ready dict, same shape hub/api.py's other endpoints use
    (web/lib/hub.js's normaliseApiItem() expects it) - shared so /api/feed's
    two implementations (hub/api.py, the Vercel function) serialize
    identically, not just parse identically."""
    return {
        "course": item.course, "category": item.category, "kind": item.kind, "title": item.title,
        "due": item.due.isoformat() if item.due else None, "url": item.url, "source": item.source,
        "done": item.done,
        "status": status_of(item, now),
        "urgency": classify_urgency(item.title, item.due, now),
    }
