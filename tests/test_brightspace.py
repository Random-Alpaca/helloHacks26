"""Tests for hub/brightspace.py.

The enrollment shape below is an anonymised copy of a real response from a
UBC course on ubc.brightspace.com (checked live, 2026-09-26): same keys,
same nesting, fake name/id/dates. See hub/brightspace.py's module docstring
for what's verified and what's deliberately left unbuilt (due dates).
"""
from hub.brightspace import to_course

# Anonymised, but structurally identical to the real
# /d2l/api/lp/1.50/enrollments/myenrollments/ response.
ENROLLMENTS_RESPONSE = {
    "PagingInfo": {"Bookmark": "12345", "HasMoreItems": False},
    "Items": [
        {
            "OrgUnit": {
                "Id": 12345,
                "Type": {"Id": 3, "Code": "Course Offering", "Name": "Course Offering"},
                "Name": "MATH_V 100A ALL SECTIONS 2026W1 Differential Calculus with Applications",
                "Code": "MATH_V 100A ALL SECTIONS 2026W1",
                "HomeUrl": "https://example.brightspace.com/d2l/home/12345",
                "ImageUrl": "https://example.brightspace.com/d2l/api/lp/1.9/courses/12345/image",
            },
            "Access": {
                "IsActive": True,
                "StartDate": "2026-09-08T07:00:00.000Z",
                "EndDate": "2027-02-02T06:59:00.000Z",
                "CanAccess": True,
                "ClasslistRoleName": "Learner",
                "LISRoles": ["urn:lti:instrole:ims/lis/Student", "urn:lti:instrole:ims/lis/Learner"],
                "LastAccessed": "2026-09-27T04:20:13.077Z",
            },
            "PinDate": None,
        }
    ],
}


def test_to_course_reads_the_real_enrollment_shape():
    course = to_course(ENROLLMENTS_RESPONSE["Items"][0])
    assert course.code == "MATH_V 100A ALL SECTIONS 2026W1"
    assert course.title == "MATH_V 100A ALL SECTIONS 2026W1 Differential Calculus with Applications"
    # No section/term field exists in this response -- left blank, not guessed.
    assert course.section == ""
    assert course.term == ""


def test_fetch_returns_courses_from_enrollments_and_no_items(monkeypatch):
    from hub import brightspace

    calls = []

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload
            self.status = 200
            self.ok = True

        def json(self):
            return self._payload

    class FakeRequest:
        def get(self, url):
            calls.append(url)
            if url.endswith("/d2l/api/lp/unstable/users/whoami"):
                return FakeResponse({"Identifier": "1", "FirstName": "Test", "LastName": "Student"})
            return FakeResponse(ENROLLMENTS_RESPONSE)

    def fake_fetch_with_session(site_name, base, run):
        assert site_name == "brightspace"
        return run(FakeRequest())

    monkeypatch.setattr(brightspace.site, "fetch_with_session", fake_fetch_with_session)

    courses, items = brightspace.fetch("https://example.brightspace.com")
    assert [c.code for c in courses] == ["MATH_V 100A ALL SECTIONS 2026W1"]
    assert items == []  # no JSON due-date endpoint found -- see module docstring
    assert any("whoami" in c for c in calls)
    assert any("enrollments" in c for c in calls)


def test_fetch_degrades_to_empty_on_any_failure(monkeypatch):
    from hub import brightspace

    def fake_fetch_with_session(site_name, base, run):
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr(brightspace.site, "fetch_with_session", fake_fetch_with_session)

    courses, items = brightspace.fetch("https://example.brightspace.com")
    assert (courses, items) == ([], [])
