"""Round-trip fixtures through to_ics(), then back through hub.ics.parse()
(#18's own test ask) - proves the feed we hand out is the same shape we
already know how to read back in, not just "some .ics text"."""

from datetime import datetime, timezone

from icalendar import Calendar as ICalendar

from hub import ics
from hub.export_ics import _uid, to_ics
from hub.models import Item

ITEM_A = Item(course="CPSC 121", category="task", kind="assignment", title="Problem Set 3",
              due=datetime(2026, 9, 30, 6, 59, tzinfo=timezone.utc),
              url="https://canvas.ubc.ca/courses/7/assignments/99", source="canvas")
ITEM_B = Item(course="MATH 100", category="deadline", kind="exam", title="Midterm 1",
              due=datetime(2026, 10, 9, 17, 0, tzinfo=timezone.utc),
              url="https://canvas.ubc.ca/courses/8/assignments/12", source="canvas")
ITEM_NO_DUE = Item(course="CPSC 121", category="task", kind="assignment", title="Reading response",
                    due=None, url="https://canvas.ubc.ca/courses/7/assignments/50", source="canvas")


def test_round_trips_title_course_due_and_url_through_hub_ics_parse():
    ics_bytes = to_ics([ITEM_A, ITEM_B])
    parsed = ics.parse(ics_bytes.decode(), source="canvas")
    assert len(parsed) == 2
    assert (parsed[0].course, parsed[0].title, parsed[0].due, parsed[0].url) == (
        ITEM_A.course, ITEM_A.title, ITEM_A.due, ITEM_A.url)
    assert (parsed[1].course, parsed[1].title, parsed[1].due, parsed[1].url) == (
        ITEM_B.course, ITEM_B.title, ITEM_B.due, ITEM_B.url)


def test_items_with_no_due_date_are_skipped_not_crashed_on():
    ics_bytes = to_ics([ITEM_A, ITEM_NO_DUE])
    parsed = ics.parse(ics_bytes.decode(), source="canvas")
    assert len(parsed) == 1
    assert parsed[0].title == "Problem Set 3"


def test_uid_is_stable_across_calls_for_the_same_item():
    assert _uid(ITEM_A) == _uid(ITEM_A)
    assert _uid(ITEM_A) != _uid(ITEM_B)


def test_uid_is_scoped_by_source_not_just_url():
    # (source, url) is the identity (rule 4) - two different sources at
    # coincidentally the same url must not collide onto one calendar event.
    same_url_other_source = Item(**{**ITEM_A.__dict__, "source": "ics"})
    assert _uid(ITEM_A) != _uid(same_url_other_source)


def test_every_event_has_two_alarms():
    ics_bytes = to_ics([ITEM_A])
    cal = ICalendar.from_ical(ics_bytes)
    event = next(c for c in cal.walk() if c.name == "VEVENT")
    alarms = [c for c in event.subcomponents if c.name == "VALARM"]
    assert len(alarms) == 2


def test_output_is_a_valid_calendar_with_no_events_for_an_empty_input():
    ics_bytes = to_ics([])
    assert b"BEGIN:VCALENDAR" in ics_bytes
    assert b"BEGIN:VEVENT" not in ics_bytes
