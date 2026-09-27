"""Tests for hub/brightspace.py.

**[unverified]** All markup below is constructed from D2L's public
documentation and publicly available Brightspace screenshots, NOT scraped
from a live instance - no Brightspace instance exists anywhere on this
project (UBC runs Canvas, not Brightspace). See hub/brightspace.py's module
docstring and docs/api-standards.md's Brightspace row for exactly what's a
documented fact vs. a guess here. These tests only confirm the parsers do
what this module's own guessed rules say they should - they are not, and
cannot be, evidence that a real Brightspace page looks like this.
"""
from bs4 import BeautifulSoup

from hub.brightspace import _agenda_items, _code_from_heading, _courses, _parse_due, to_course, to_item

# [unverified] Guessed "My Courses" page: a link per course tile to its
# homepage at the one documented URL shape, `/d2l/home/<orgUnitId>`.
COURSE_LIST_HTML = """
<div class="d2l-list">
  <a class="d2l-link" href="/d2l/home/12345">CPSC 121 101 (2026W1): Models of Computation</a>
  <a class="d2l-link" href="/d2l/home/67890">MATH 200 201 (2026W1): Calculus III</a>
  <a href="/d2l/lp/navbar/whatever">Not a course tile</a>
</div>
"""

# [unverified] Guessed Calendar Agenda view, "group by Course" mode: a
# heading per course, then its list-items, mirroring the same "heading row,
# then item rows" shape hub/prairielearn.py's assessments table already uses.
AGENDA_HTML = """
<div class="d2l-list">
  <h3 class="d2l-heading" data-brightspace-heading>CPSC 121 101</h3>
  <div class="d2l-list-item">
    <a href="/d2l/le/content/12345/viewContent/555/View" data-kind="assignment">Assignment 3: Recursion</a>
    <span class="d2l-body-small">Sep 27, 2026 11:59 PM</span>
  </div>
  <div class="d2l-list-item">
    <a href="/d2l/le/content/12345/viewContent/556/View" data-kind="quiz">Quiz 4</a>
    <span class="d2l-body-small">Oct 3, 2026 9:00 AM</span>
  </div>
  <h3 class="d2l-heading" data-brightspace-heading>MATH 200 201</h3>
  <div class="d2l-list-item">
    <a href="/d2l/le/content/67890/viewContent/999/View" data-kind="dropbox">Problem Set 2</a>
    <span class="d2l-body-small">Sep 30, 2026 11:59 PM</span>
  </div>
  <div class="d2l-list-item">
    <span class="text-muted">No date shown yet</span>
  </div>
</div>
"""


def soup(html):
    return BeautifulSoup(html, "html.parser")


def test_course_tile_parses_code_section_term_title():
    c = to_course("CPSC 121 101 (2026W1): Models of Computation")
    assert (c.code, c.section, c.term, c.title) == ("CPSC 121", "101", "2026W1", "Models of Computation")


def test_course_tile_falls_back_to_raw_text_on_unexpected_format():
    # ponytail-equivalent: the guessed format is unconfirmed, so an
    # unexpected tile must not crash the adapter, just degrade gracefully.
    c = to_course("Some Weird Tile With No Structure")
    assert c.code == "Some Weird Tile With No Structure"
    assert c.section == "" and c.term == ""


def test_courses_only_picks_up_home_links_with_numeric_org_unit_id():
    courses = _courses(soup(COURSE_LIST_HTML))
    assert [c.code for c in courses] == ["CPSC 121", "MATH 200"]
    assert [c.section for c in courses] == ["101", "201"]


def test_code_from_heading_extracts_code_and_section():
    assert _code_from_heading("CPSC 121 101") == "CPSC 121 101"


def test_parse_due_reads_guessed_agenda_date_format():
    due = _parse_due("Sep 27, 2026 11:59 PM")
    assert due.isoformat() == "2026-09-27T23:59:00-07:00"
    assert due.tzinfo is not None  # never a naive datetime in the shared model


def test_parse_due_am_midnight_hour_rolls_over_correctly():
    due = _parse_due("Oct 3, 2026 9:00 AM")
    assert due.hour == 9


def test_parse_due_returns_none_when_text_does_not_match():
    assert _parse_due("No date shown yet") is None
    assert _parse_due(None) is None


def test_to_item_reads_kind_title_url_and_due():
    entry = soup(AGENDA_HTML).select("div.d2l-list-item")[0]
    i = to_item(entry, "CPSC 121 101")
    assert i.course == "CPSC 121 101"
    assert (i.category, i.kind) == ("task", "assignment")
    assert i.title == "Assignment 3: Recursion"
    assert i.url == "/d2l/le/content/12345/viewContent/555/View"
    assert i.due.isoformat() == "2026-09-27T23:59:00-07:00"
    assert i.source == "brightspace"


def test_to_item_maps_dropbox_and_quiz_kinds():
    entries = soup(AGENDA_HTML).select("div.d2l-list-item")
    assert to_item(entries[1], "CPSC 121 101").kind == "quiz"
    assert to_item(entries[2], "MATH 200 201").kind == "assignment"  # dropbox -> assignment


def test_to_item_with_no_link_or_date_does_not_crash():
    entry = soup(AGENDA_HTML).select("div.d2l-list-item")[3]
    i = to_item(entry, "MATH 200 201")
    assert i.url == ""
    assert i.due is None
    assert i.title == "No date shown yet"


def test_agenda_items_groups_by_course_heading():
    items = _agenda_items(soup(AGENDA_HTML))
    assert [(i.course, i.title) for i in items] == [
        ("CPSC 121 101", "Assignment 3: Recursion"),
        ("CPSC 121 101", "Quiz 4"),
        ("MATH 200 201", "Problem Set 2"),
        ("MATH 200 201", "No date shown yet"),
    ]
