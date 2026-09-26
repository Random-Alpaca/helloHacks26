from hub.canvas import to_course, to_item, unwrap


def test_unwrap_strips_guard():
    assert unwrap('while(1);[{"id": 1}]') == [{"id": 1}]
    assert unwrap('[]') == []


def test_mapping():
    c = to_course({"id": 7, "course_code": "CPSC 121", "name": "Models of Computation",
                   "term": {"name": "2026W1"}, "enrollments": [{"computed_current_score": 88.5}]})
    assert (c.code, c.term, c.grade) == ("CPSC 121", "2026W1", 88.5)
    i = to_item({"course_id": 7, "plannable_type": "quiz", "plannable_date": "2026-09-30T06:59:00Z",
                 "plannable": {"title": "Quiz 2"}, "html_url": "/courses/7/quizzes/3"}, {7: "CPSC 121"})
    assert (i.course, i.kind, i.title, i.due.day) == ("CPSC 121", "assignment", "Quiz 2", 30)
    assert i.url == "https://canvas.ubc.ca/courses/7/quizzes/3"
    assert to_item({"plannable_type": "calendar_event", "plannable": {}}, {}).kind == "event"
