from hub.logic import normalise_course_code


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
