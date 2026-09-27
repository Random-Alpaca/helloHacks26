"""Export the shared model as one merged .ics feed a student can subscribe to
from Apple/Google/Outlook Calendar (#18) - the cheapest way into a routine
they already have, and the reverse direction of hub/ics.py's inbound parser.

Try it:  uv run python -m hub.export_ics
"""
import hashlib
from datetime import timedelta

from icalendar import Alarm, Calendar, Event

# Two reminders per item, matching the pattern from Terrace's own
# course-deadline calendars: a heads-up two days out, and one on the day.
ALARM_DAYS_BEFORE = (2, 0)


def _uid(item):
    """Stable across re-exports: a hash of the item's own (source, url)
    identity (rule 4), not a counter that resets between runs - re-importing
    the same feed updates existing calendar events instead of duplicating
    them."""
    digest = hashlib.sha1(f"{item.source}:{item.url}".encode()).hexdigest()[:16]
    return f"{item.source}-{digest}@ubchub"


def _alarm(days_before, summary):
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", summary)
    alarm.add("trigger", timedelta(days=-days_before))
    return alarm


def to_ics(items):
    """[Item] -> one merged .ics feed, as bytes. Items with no due date are
    skipped - there's no date to put a calendar event on (they still show up
    in the dashboard itself, just not here).

    Titles get Canvas's own "Title [COURSE]" bracket suffix - the exact
    convention hub.ics.parse() already reads a course code out of, so this
    feed round-trips back through our own inbound parser (tests/
    test_export_ics.py), not just out to a phone's calendar app."""
    cal = Calendar()
    cal.add("prodid", "-//UBC Hub//ubchub//EN")
    cal.add("version", "2.0")
    for item in items:
        if item.due is None:
            continue
        summary = f"{item.title} [{item.course}]" if item.course else item.title
        event = Event()
        event.add("uid", _uid(item))
        event.add("summary", summary)
        event.add("dtstart", item.due)
        if item.url:
            event.add("url", item.url)
        for days_before in ALARM_DAYS_BEFORE:
            event.add_component(_alarm(days_before, summary))
        cal.add_component(event)
    return cal.to_ical()


if __name__ == "__main__":
    from datetime import datetime

    from hub import db
    from hub.models import Item

    conn = db.connect()
    items = [
        Item(course=code, category=category, kind=kind, title=title,
             due=datetime.fromisoformat(due) if due else None, url=url, source=source,
             done=bool(done) if done is not None else None)
        for code, category, kind, title, due, url, done, source in db.upcoming(conn)
    ]
    print(to_ics(items).decode())
