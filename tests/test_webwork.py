from bs4 import BeautifulSoup

from hub.webwork import due_from_text, to_item

# NOT scraped from a live course - constructed to match WeBWorK's documented/
# publicly-known problem-set-list table shape (WeBWorK is open source; its
# ProblemSets.pm template is public). See hub/webwork.py's module docstring:
# this is [unverified] against a real live instance.
OPEN_ROW = """
<tr>
  <td>1</td>
  <td><a href="/webwork2/math101/HW1/">HW1</a></td>
  <td>09/07/2026 at 09:00am PDT</td>
  <td>09/14/2026 at 11:59pm PDT</td>
  <td>0%</td>
</tr>
"""

DONE_ROW = """
<tr>
  <td>2</td>
  <td><a href="/webwork2/math101/HW2/">HW2</a></td>
  <td>09/14/2026 at 09:00am PDT</td>
  <td>09/21/2026 at 11:59pm PDT</td>
  <td>100%</td>
</tr>
"""

# A set that hasn't opened yet: no link, no due date - a header/placeholder
# row rather than a real set (mirrors prairielearn's "not open yet" case).
HEADER_ROW = """
<tr>
  <th>Set</th>
  <th>Opens</th>
  <th>Due</th>
  <th>Grade</th>
</tr>
"""


def row(html):
    return BeautifulSoup(html, "html.parser").find("tr")


def test_open_set_gets_due_date_and_resolved_link():
    i = to_item(row(OPEN_ROW), "MATH 101", base="https://webwork.example.edu/")
    assert (i.category, i.kind, i.title) == ("task", "problemset", "HW1")
    assert i.due.isoformat() == "2026-09-14T23:59:00-07:00"
    assert i.url == "https://webwork.example.edu/webwork2/math101/HW1/"
    assert i.source == "webwork"


def test_due_is_never_naive():
    i = to_item(row(OPEN_ROW), "MATH 101")
    assert i.due.tzinfo is not None


def test_incomplete_set_has_unknown_done_not_false():
    # 0% could mean "not started" or "graded zero" - we don't guess, so
    # `done` stays None (unknown) rather than False.
    i = to_item(row(OPEN_ROW), "MATH 101")
    assert i.done is None


def test_100pct_set_is_done():
    i = to_item(row(DONE_ROW), "MATH 101")
    assert i.done is True


def test_header_row_has_no_link_or_due():
    # to_item shouldn't be called on a header row in practice (the caller
    # filters those out), but it should degrade gracefully rather than crash
    # if it ever is.
    i = to_item(row(HEADER_ROW), "MATH 101")
    assert i.due is None
    assert i.url == ""


def test_due_from_text_parses_documented_format():
    dt = due_from_text("09/14/2026 at 11:59pm PDT")
    assert dt.isoformat() == "2026-09-14T23:59:00-07:00"


def test_due_from_text_handles_am_and_unknown_timezone():
    dt = due_from_text("01/05/2026 at 9:00am")
    assert dt.isoformat() == "2026-01-05T09:00:00+00:00"


def test_due_from_text_none_for_blank_or_missing_date():
    assert due_from_text("") is None
    assert due_from_text("n/a") is None
    assert due_from_text(None) is None
