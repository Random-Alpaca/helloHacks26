from hub.workday import parse_workday_courses

FIXTURE = "fixtures/workday_view_my_courses.xlsx"


def test_parses_all_course_rows():
    courses = parse_workday_courses(FIXTURE, term="2026W1")
    assert [c.code for c in courses] == ["CPSC 121", "MATH 200", "CPSC 210"]


def test_fields_from_first_row():
    courses = parse_workday_courses(FIXTURE, term="2026W1")
    cpsc121 = courses[0]
    assert cpsc121.section == "001"
    assert cpsc121.term == "2026W1"
    assert cpsc121.title == "Models of Computation"


def test_missing_section_still_parses():
    courses = parse_workday_courses(FIXTURE, term="2026W1")
    cpsc210 = courses[2]
    assert cpsc210.section is None
    assert cpsc210.title == "Software Construction"
