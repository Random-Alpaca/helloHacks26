from datetime import datetime, timezone

from hub.logic import normalise_course_code, sort_items
from hub.models import Item


def _item(id, due=None):
    return Item(id=id, course_key="c", kind="assignment", title=id, source="canvas", due=due)


def test_full_code_with_term():
    # Space-separated, includes a term at the end that this function ignores.
    assert normalise_course_code("CPSC 121 101 2026W1") == ("CPSC", "121", "101")


def test_underscore_campus_marker_and_dash_section():
    # "_V" is a campus marker (UBC-specific) and gets dropped so the logic
    # generalises to schools that don't use campus markers at all.
    assert normalise_course_code("CPSC_V 121-101") == ("CPSC", "121", "101")


def test_no_spaces_no_section():
    # Lowercase, no section given at all.
    assert normalise_course_code("cpsc121") == ("CPSC", "121", None)


def test_short_faculty_and_short_number():
    # 2-letter faculty, 2-digit course number (e.g. a school like "CS 61").
    assert normalise_course_code("CS 61") == ("CS", "61", None)


def test_long_faculty_and_long_number():
    # 5-letter faculty, 4-digit course number.
    assert normalise_course_code("STATS 1110") == ("STATS", "1110", None)


def test_unparseable_garbage():
    assert normalise_course_code("!!!") == (None, None, None)


def test_sort_items_by_due_date_no_due_date_last():
    soon = _item("soon", due=datetime(2026, 10, 1, tzinfo=timezone.utc))
    later = _item("later", due=datetime(2026, 10, 15, tzinfo=timezone.utc))
    no_due = _item("no_due")

    result = sort_items([later, no_due, soon])

    assert [item.id for item in result] == ["soon", "later", "no_due"]
