from datetime import datetime, timedelta, timezone

from hub.logic import dedupe, delete_item, normalise_course_code, sort_items, suspected_duplicates
from hub.models import Item, category_for

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def row(title, due_offset_hours):
    due = (NOW + timedelta(hours=due_offset_hours)).isoformat()
    return ("CPSC 121", "task", "assignment", title, due, "https://x", None)


def test_overdue_beats_everything():
    rows = [row("Reading 4", 5), row("Final Exam", -1)]
    assert sort_items(rows, NOW)[0][3] == "Final Exam"


def test_critical_beats_low_even_if_further_out():
    rows = [row("Optional practice quiz, 0%", 2), row("Final exam", 20)]
    ordered = sort_items(rows, NOW)
    assert ordered[0][3] == "Final exam"


def _item(id, due=None, done=None):
    return Item(
        course="CPSC 121", category=category_for("assignment"), kind="assignment",
        title=id, due=due, url=f"https://example.invalid/{id}", source="canvas",
        done=done,
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


def test_delete_item_removes_only_matching_source_and_url():
    items = [_item("a"), _item("b"), _item("c")]
    result = delete_item(items, "canvas", "https://example.invalid/b")
    assert [item.title for item in result] == ["a", "c"]


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


def test_suspected_duplicates_flags_fuzzy_title_and_close_due_across_sources():
    due = datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc)
    canvas_item = _item("Homework 3: Recursion")
    canvas_item.due = due
    pl_item = Item(
        course="CPSC 121", category=category_for("assignment"), kind="assignment",
        title="hw3 recursion", due=due - timedelta(hours=1),
        url="https://example.invalid/pl3", source="prairielearn",
    )
    pairs = suspected_duplicates([canvas_item, pl_item])
    assert pairs == [(canvas_item, pl_item)]


def test_suspected_duplicates_ignores_far_apart_due_dates():
    canvas_item = _item("Homework 3: Recursion")
    canvas_item.due = datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc)
    pl_item = Item(
        course="CPSC 121", category=category_for("assignment"), kind="assignment",
        title="hw3 recursion", due=datetime(2026, 10, 5, 23, 59, tzinfo=timezone.utc),
        url="https://example.invalid/pl3", source="prairielearn",
    )
    assert suspected_duplicates([canvas_item, pl_item]) == []


def test_suspected_duplicates_ignores_unrelated_titles_even_with_same_due():
    due = datetime(2026, 10, 2, 23, 59, tzinfo=timezone.utc)
    canvas_item = _item("Midterm 1")
    canvas_item.due = due
    pl_item = Item(
        course="CPSC 121", category=category_for("assignment"), kind="assignment",
        title="Lab 4 checkoff", due=due, url="https://example.invalid/pl4", source="prairielearn",
    )
    assert suspected_duplicates([canvas_item, pl_item]) == []
