from datetime import datetime, timedelta, timezone

from hub.logic import dedupe, delete_item, flag, normalise_course_code, sort_items
from hub.models import Item


def _item(id, due=None, done=False):
    return Item(
        id=id, course_key="c", kind="assignment", title=id, source="canvas",
        due=due, done=done,
    )


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


NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def test_flag_overdue():
    item = _item("a", due=NOW - timedelta(hours=1))
    assert flag(item, NOW) == "overdue"


def test_flag_soon():
    item = _item("a", due=NOW + timedelta(hours=24))
    assert flag(item, NOW) == "soon"


def test_flag_not_urgent():
    item = _item("a", due=NOW + timedelta(days=7))
    assert flag(item, NOW) is None


def test_flag_no_due_date():
    item = _item("a")
    assert flag(item, NOW) is None


def test_flag_done_past_due_is_not_overdue():
    # Canvas rule: submitted work never shows as overdue, even if it was late.
    item = _item("a", due=NOW - timedelta(hours=1), done=True)
    assert flag(item, NOW) is None


def test_delete_item_removes_only_matching_id():
    items = [_item("a"), _item("b"), _item("c")]
    result = delete_item(items, "b")
    assert [item.id for item in result] == ["a", "c"]


class _DedupeItem:
    # Stand-in for whatever the real Item ends up being — dedupe() only
    # needs .course, .title and .due, duck-typed, so it doesn't care.
    def __init__(self, label, course, title, due):
        self.label = label
        self.course = course
        self.title = title
        self.due = due


def test_dedupe_same_course_title_due_counts_as_one():
    due = datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc)
    from_canvas = _DedupeItem("canvas", "CPSC 121", "Problem Set 3", due)
    from_ics = _DedupeItem("ics", "CPSC 121", "Problem Set 3", due)
    different = _DedupeItem("other", "CPSC 121", "Problem Set 4", due)

    result = dedupe([from_canvas, from_ics, different])

    assert [item.label for item in result] == ["canvas", "other"]
