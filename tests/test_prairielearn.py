from bs4 import BeautifulSoup

from hub.prairielearn import due_from_popover, to_course, to_item

# Real markup captured from a live UBC PrairieLearn course (CPSC 317, 2026W1).
OPEN_ROW = """
<tr>
  <td class="align-middle" style="width: 1%"><span data-testid="assessment-set-badge">PA1</span></td>
  <td class="align-middle"><a href="/pl/course_instance/221053/assessment_instance/14835025/">A Dictionary Client</a></td>
  <td class="text-center align-middle">
    100% until 23:59, Sun, Sep 27
    <button data-bs-content="
    &lt;table&gt;
      &lt;tr&gt;&lt;th&gt;Credit&lt;/th&gt;&lt;th&gt;Start&lt;/th&gt;&lt;th&gt;End&lt;/th&gt;&lt;/tr&gt;
      &lt;tr&gt;&lt;td&gt;100&lt;/td&gt;&lt;td&gt;2026-09-14 09:00:00 (PDT)&lt;/td&gt;&lt;td&gt;2026-09-27 23:59:59 (PDT)&lt;/td&gt;&lt;/tr&gt;
      &lt;tr&gt;&lt;td&gt;70&lt;/td&gt;&lt;td&gt;2026-09-27 23:59:59 (PDT)&lt;/td&gt;&lt;td&gt;2026-10-04 23:59:59 (PDT)&lt;/td&gt;&lt;/tr&gt;
      &lt;tr&gt;&lt;td&gt;0&lt;/td&gt;&lt;td&gt;2026-10-11 23:59:59 (PDT)&lt;/td&gt;&lt;td&gt;—&lt;/td&gt;&lt;/tr&gt;
    &lt;/table&gt;
  "></button>
  </td>
  <td class="text-center align-middle">100%</td>
</tr>
"""
NOT_OPEN_ROW = """
<tr>
  <td class="align-middle" style="width: 1%"><span data-testid="assessment-set-badge">PA2</span></td>
  <td class="align-middle"><span class="text-muted">Implementing a DNS Client</span></td>
  <td class="text-center align-middle"><span class="text-muted">Available 09:00, Mon, Sep 28</span></td>
  <td class="text-center align-middle">Not started</td>
</tr>
"""


def row(html):
    return BeautifulSoup(html, "html.parser").find("tr")


def test_open_assessment_gets_due_from_100pct_tier_and_a_link():
    i = to_item(row(OPEN_ROW), "CPSC 317", "Programming Assignments")
    assert (i.category, i.kind, i.title) == ("task", "assignment", "A Dictionary Client")
    assert i.due.isoformat() == "2026-09-27T23:59:59"
    assert i.url == "https://us.prairielearn.com/pl/course_instance/221053/assessment_instance/14835025/"


def test_not_yet_open_assessment_has_no_due_or_link():
    i = to_item(row(NOT_OPEN_ROW), "CPSC 317", "Programming Assignments")
    assert i.due is None
    assert i.url == ""


def test_group_heading_maps_quiz_and_exam():
    assert to_item(row(OPEN_ROW), "CPSC 317", "Practice for Quizzes").kind == "quiz"
    assert to_item(row(OPEN_ROW), "CPSC 317", "Formal Quizzes (repeated for practice)").kind == "exam"


def test_last_tier_with_no_end_date_is_none():
    assert due_from_popover(None) is None


def test_course_title_parsing():
    c = to_course("221053", "CPSC 317: Internet Computing, 2026 Winter Term 1")
    assert (c.code, c.title, c.term) == ("CPSC 317", "Internet Computing", "2026 Winter Term 1")
