import pytest
from bs4 import BeautifulSoup

from hub.prairielearn import due_from_popover, resolve_campus, to_course, to_item

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
    i = to_item(row(OPEN_ROW), "CPSC 317", "Programming Assignments", "prairielearn", "https://us.prairielearn.com")
    assert (i.category, i.kind, i.title) == ("task", "assignment", "A Dictionary Client")
    assert i.due.isoformat() == "2026-09-27T23:59:59-07:00"  # PDT, timezone-aware like Canvas's due dates
    assert i.url == "https://us.prairielearn.com/pl/course_instance/221053/assessment_instance/14835025/"


def test_due_is_never_naive():
    # A naive due here would crash any code that compares it against
    # datetime.now(timezone.utc) - e.g. Terrace's "Hide overdue" toggle.
    i = to_item(row(OPEN_ROW), "CPSC 317", "Programming Assignments", "prairielearn", "https://us.prairielearn.com")
    assert i.due.tzinfo is not None


def test_not_yet_open_assessment_has_no_due_or_link():
    i = to_item(row(NOT_OPEN_ROW), "CPSC 317", "Programming Assignments", "prairielearn", "https://us.prairielearn.com")
    assert i.due is None
    assert i.url == ""


def test_group_heading_maps_quiz_and_exam():
    base = "https://us.prairielearn.com"
    assert to_item(row(OPEN_ROW), "CPSC 317", "Practice for Quizzes", "prairielearn", base).kind == "quiz"
    assert to_item(row(OPEN_ROW), "CPSC 317", "Formal Quizzes (repeated for practice)", "prairielearn", base).kind == "exam"


def test_last_tier_with_no_end_date_is_none():
    assert due_from_popover(None) is None


def test_course_title_parsing():
    c = to_course("221053", "CPSC 317: Internet Computing, 2026 Winter Term 1")
    assert (c.code, c.title, c.term) == ("CPSC 317", "Internet Computing", "2026 Winter Term 1")


def test_okanagan_campus_gets_its_own_base_url_and_source():
    # A real student found their MECH 260 assessments live on UBC Okanagan's
    # own PrairieLearn instance, not the shared us.prairielearn.com one -
    # each campus needs its own base URL and its own `source`, so the two
    # never collide under the same (source, url) identity.
    i = to_item(row(OPEN_ROW), "MECH 260", "Programming Assignments", "prairielearn_ok", "https://prairielearn.ok.ubc.ca")
    assert i.source == "prairielearn_ok"
    assert i.url == "https://prairielearn.ok.ubc.ca/pl/course_instance/221053/assessment_instance/14835025/"


def test_resolve_campus_known_key():
    assert resolve_campus("prairielearn_ok") == ("prairielearn_ok", "https://prairielearn.ok.ubc.ca")


def test_resolve_campus_pasting_a_known_instances_own_url_resolves_to_its_key():
    # A real account connected UBC Okanagan's instance both via the
    # quick-connect button (key "prairielearn_ok") and by pasting its URL
    # directly - without this, the second path produces source
    # "prairielearn.ok.ubc.ca", a different value for the same real
    # instance, so it shows up as two separate connections with duplicated
    # items.
    assert resolve_campus("https://prairielearn.ok.ubc.ca") == ("prairielearn_ok", "https://prairielearn.ok.ubc.ca")


def test_resolve_campus_accepts_a_pasted_url_for_an_unlisted_instance():
    # Any department can self-host their own PrairieLearn (a second, distinct
    # UBC Okanagan instance turned up in the same search that found the
    # first one) - a hardcoded list can never be complete, so a full URL
    # works even when it's not one of the known CAMPUSES keys.
    key, base = resolve_campus("https://pl.autoed.ok.ubc.ca")
    assert (key, base) == ("pl.autoed.ok.ubc.ca", "https://pl.autoed.ok.ubc.ca")


def test_resolve_campus_strips_a_path_down_to_just_the_host():
    # A student pasting the login page URL rather than the bare domain
    # shouldn't produce a broken/duplicated base.
    assert resolve_campus("https://pl.autoed.ok.ubc.ca/pl/login") == ("pl.autoed.ok.ubc.ca", "https://pl.autoed.ok.ubc.ca")


@pytest.mark.parametrize("bad", ["http://pl.autoed.ok.ubc.ca", "not a url", "javascript:alert(1)", ""])
def test_resolve_campus_rejects_anything_that_isnt_a_real_https_url(bad):
    # This opens a real login browser window at whatever's returned - a typo
    # or a non-URL string must fail loudly here, not reach Playwright.
    with pytest.raises(ValueError):
        resolve_campus(bad)
