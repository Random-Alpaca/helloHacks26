"""One iCalendar parser for any school's feed (Canvas, Moodle, ...).

Canvas and Moodle both expose a per-student .ics URL (docs/api-standards.md
"Architecture suggestion"). Feed URLs carry a secret, same as a token: never
log or commit one.
"""
import re

import requests
from icalendar import Calendar

from hub.models import Item, category_for

# Canvas puts "[COURSE CODE]" on the end of every event/assignment summary.
# Moodle feeds don't, so course comes back "" there - fine for a first cut.
COURSE_SUFFIX = re.compile(r"\s*\[(.+?)\]\s*$")


def parse(ics_text, source):
    """.ics text -> list[Item]. `source` tags where it came from, e.g. "canvas"."""
    items = []
    for event in Calendar.from_ical(ics_text).walk("VEVENT"):
        summary = str(event.get("summary", ""))
        m = COURSE_SUFFIX.search(summary)
        dtstart = event.get("dtstart")
        url = str(event.get("url", ""))
        # ponytail: ics has no assignment/event/announcement flag; "/calendar_events/"
        # in the link is the only signal Canvas gives us. Good enough for "what's due".
        kind = "event" if "/calendar_events/" in url else "assignment"
        items.append(Item(
            course=m.group(1) if m else "",
            category=category_for(kind),
            kind=kind,
            title=COURSE_SUFFIX.sub("", summary),
            due=dtstart.dt if dtstart else None,
            url=url,
            source=source,
        ))
    return items


def fetch(feed_url, source):
    """Feed URL -> list[Item]. Raises requests.HTTPError on a bad/expired URL."""
    r = requests.get(feed_url, timeout=30)
    r.raise_for_status()
    return parse(r.text, source)
