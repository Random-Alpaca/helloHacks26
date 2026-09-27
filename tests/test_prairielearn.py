import pytest
from bs4 import BeautifulSoup

from hub.prairielearn import due_from_popover, to_course, to_item, _course_instances

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
    i = to_item(row(OPEN_ROW), "CPSC 317", "Programming Assignments", "221053")
    assert (i.category, i.kind, i.title) == ("task", "assignment", "A Dictionary Client")
    assert i.due.isoformat() == "2026-09-27T23:59:59-07:00"  # PDT, timezone-aware like Canvas's due dates
    assert i.url == "https://us.prairielearn.com/pl/course_instance/221053/assessment_instance/14835025/"


def test_due_is_never_naive():
    # A naive due here would crash any code that compares it against
    # datetime.now(timezone.utc) - e.g. Terrace's "Hide overdue" toggle.
    i = to_item(row(OPEN_ROW), "CPSC 317", "Programming Assignments", "221053")
    assert i.due.tzinfo is not None


def test_not_yet_open_assessment_has_no_due_and_a_fallback_identity_url():
    # A blank url here used to mean every unreleased assessment across every
    # course collided onto one hub.db row, since identity is (source, url).
    i = to_item(row(NOT_OPEN_ROW), "CPSC 317", "Programming Assignments", "221053")
    assert i.due is None
    assert i.url == "https://us.prairielearn.com/pl/course_instance/221053/assessments#Implementing%20a%20DNS%20Client"


def test_group_heading_maps_quiz_and_exam():
    assert to_item(row(OPEN_ROW), "CPSC 317", "Practice for Quizzes", "221053").kind == "quiz"
    assert to_item(row(OPEN_ROW), "CPSC 317", "Formal Quizzes (repeated for practice)", "221053").kind == "exam"


def test_last_tier_with_no_end_date_is_none():
    assert due_from_popover(None) is None


def test_mst_is_a_recognized_offset_alongside_pst_and_pdt():
    popover = OPEN_ROW.replace("(PDT)", "(MST)")
    i = to_item(row(popover), "CPSC 317", "Programming Assignments", "221053")
    assert i.due.utcoffset().total_seconds() / 3600 == -7


def test_unrecognized_timezone_abbreviation_raises_instead_of_silently_using_utc():
    popover = OPEN_ROW.replace("(PDT)", "(XYZ)")
    with pytest.raises(ValueError):
        to_item(row(popover), "CPSC 317", "Programming Assignments", "221053")


def test_course_title_parsing():
    c = to_course("221053", "CPSC 317: Internet Computing, 2026 Winter Term 1")
    assert (c.code, c.title, c.term) == ("CPSC 317", "Internet Computing", "2026 Winter Term 1")


class _FakeReq:
    def __init__(self, html):
        self.html = html

    def get(self, url):
        return self

    @property
    def status(self):
        return 200

    @property
    def ok(self):
        return True

    def text(self):
        return self.html


def test_course_instances_matches_both_student_and_instructor_links():
    html = """
    <a href="/pl/course_instance/1">CPSC 317</a>
    <a href="/pl/course_instance/2/instructor">CPSC 121 (TA)</a>
    """
    assert _course_instances(_FakeReq(html)) == [("1", "CPSC 317"), ("2", "CPSC 121 (TA)")]
