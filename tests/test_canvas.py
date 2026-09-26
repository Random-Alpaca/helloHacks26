from hub.canvas import next_link, parse_json, to_course, to_item


def test_parse_json_strips_guard():
    assert parse_json('while(1);[{"id": 1}]') == [{"id": 1}]
    assert parse_json('[]') == []


def test_next_link():
    h = '<https://canvas.ubc.ca/api/v1/courses?page=2>; rel="next", <https://canvas.ubc.ca/api/v1/courses?page=1>; rel="first"'
    assert next_link(h) == "https://canvas.ubc.ca/api/v1/courses?page=2"
    assert next_link('<x>; rel="last"') is None
    assert next_link(None) is None


def test_mapping():
    c = to_course({"id": 7, "course_code": "CPSC 121", "name": "Models of Computation",
                   "term": {"name": "2026W1"}, "enrollments": [{"computed_current_score": 88.5}]})
    assert (c.code, c.term, c.grade) == ("CPSC 121", "2026W1", 88.5)
    i = to_item({"course_id": 7, "plannable_type": "quiz", "plannable_date": "2026-09-30T06:59:00Z",
                 "plannable": {"title": "Quiz 2"}, "html_url": "/courses/7/quizzes/3"}, {7: "CPSC 121"})
    assert (i.course, i.kind, i.title, i.due.day) == ("CPSC 121", "assignment", "Quiz 2", 30)
    assert i.url == "https://canvas.ubc.ca/courses/7/quizzes/3"
    assert to_item({"plannable_type": "calendar_event", "plannable": {}}, {}).kind == "event"
