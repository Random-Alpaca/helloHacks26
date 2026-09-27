from hub.canvas import done_from_submissions, to_course, to_item, to_undated_item, unwrap


def test_unwrap_strips_guard():
    assert unwrap('while(1);[{"id": 1}]') == [{"id": 1}]
    assert unwrap('[]') == []


def test_mapping():
    c = to_course({"id": 7, "course_code": "CPSC 121", "name": "Models of Computation",
                   "term": {"name": "2026W1"}, "enrollments": [{"computed_current_score": 88.5}]})
    assert (c.code, c.term, c.grade) == ("CPSC 121", "2026W1", 88.5)
    i = to_item({"course_id": 7, "plannable_type": "quiz", "plannable_date": "2026-09-30T06:59:00Z",
                 "plannable": {"title": "Quiz 2"}, "html_url": "/courses/7/quizzes/3"}, {7: "CPSC 121"})
    assert (i.course, i.category, i.kind, i.title, i.due.day) == ("CPSC 121", "deadline", "quiz", "Quiz 2", 30)
    assert i.url == "https://canvas.ubc.ca/courses/7/quizzes/3"
    event = to_item({"plannable_type": "calendar_event", "plannable": {}}, {})
    assert (event.kind, event.category) == ("event", "deadline")
    assignment = to_item({"plannable_type": "discussion_topic", "plannable": {}}, {})
    assert (assignment.kind, assignment.category) == ("assignment", "task")


def test_calendar_event_url_is_not_double_prefixed():
    # planner/items' html_url is already absolute for calendar events, unlike
    # assignments' relative one - BASE + url used to double it (#15).
    event = to_item({"plannable_type": "calendar_event",
                     "plannable": {"title": "Office hours"},
                     "html_url": "https://canvas.ubc.ca/calendar?event_id=9"}, {})
    assert event.url == "https://canvas.ubc.ca/calendar?event_id=9"


def test_to_undated_item():
    a = {"name": "Reading response", "html_url": "/courses/7/assignments/9",
         "has_submitted_submissions": True}
    i = to_undated_item(a, "CPSC 121")
    assert (i.course, i.kind, i.category, i.title, i.due, i.done) == (
        "CPSC 121", "assignment", "task", "Reading response", None, True)
    assert i.url == "https://canvas.ubc.ca/courses/7/assignments/9"


def test_announcement_has_no_due_date():
    # plannable_date on an announcement is its post date, not a deadline -
    # verified against a real planner/items response. Using it as `due`
    # made every announcement look permanently overdue.
    announcement = to_item({"plannable_type": "announcement", "plannable_date": "2026-01-05T12:00:00Z",
                             "plannable": {"title": "Welcome!"}, "html_url": "/courses/7/announcements/1"}, {})
    assert announcement.due is None
    assert announcement.category == "task"


def test_done_from_submissions():
    # Real shapes seen from planner/items: a dict for anything gradeable,
    # a bare `false` for announcements/events - nothing to report there.
    assert done_from_submissions({"submissions": {"submitted": True, "excused": False}}) is True
    assert done_from_submissions({"submissions": {"submitted": False, "excused": True}}) is True
    assert done_from_submissions({"submissions": {"submitted": False, "excused": False}}) is False
    assert done_from_submissions({"submissions": False}) is None
    assert done_from_submissions({}) is None


def test_done_from_submissions_also_honors_the_manual_complete_checkbox():
    # A student can tick an item off Canvas's own to-do list without
    # submitting anything (e.g. a reading with no submission at all) - that
    # used to keep showing up here as not-done forever.
    assert done_from_submissions({"submissions": False, "planner_override": {"marked_complete": True}}) is True
    assert done_from_submissions({"planner_override": {"marked_complete": True}}) is True
    assert done_from_submissions({"submissions": {"submitted": False}, "planner_override": {"marked_complete": False}}) is False
    assert done_from_submissions({"planner_override": None}) is None
