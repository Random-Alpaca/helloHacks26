from datetime import timezone

import pytest

from hub import ics
from hub.ics import is_allowed_feed_host, parse

# Verified shape from a real self-hosted Canvas feed (#47): every event's URL
# is the *generic* course calendar page, never its own page - items 1 and 2
# share the exact same URL here on purpose, the real bug that broke both
# kind and (source, url) identity before the UID-based fix.
FEED = """\
BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:event-assignment-99
DTSTART:20260930T065900Z
SUMMARY:Quiz 2 [CPSC 121 101]
URL:https://canvas.ubc.ca/calendar?include_contexts=course_7
END:VEVENT
BEGIN:VEVENT
UID:event-calendar-event-55
DTSTART:20261002T170000Z
SUMMARY:Office hours [CPSC 121 101]
URL:https://canvas.ubc.ca/calendar?include_contexts=course_7
END:VEVENT
BEGIN:VEVENT
UID:event-assignment-101
DTSTART;VALUE=DATE:20261005
SUMMARY:Reading week starts [CPSC 121 101]
URL:https://canvas.ubc.ca/calendar?include_contexts=course_7
END:VEVENT
BEGIN:VEVENT
UID:3
DTSTART:20261010T000000Z
SUMMARY:Untagged item
END:VEVENT
END:VCALENDAR
"""


def test_kind_comes_from_uid_not_the_generic_url():
    items = parse(FEED, source="canvas")
    assert [i.kind for i in items] == ["assignment", "event", "assignment", "assignment"]
    assert [i.category for i in items] == ["task", "deadline", "task", "task"]
    assert items[0].course == "CPSC 121 101"
    assert items[0].title == "Quiz 2"
    assert items[0].due.day == 30


def test_deep_link_is_rebuilt_from_uid_and_course_id_not_the_generic_url():
    items = parse(FEED, source="canvas")
    assert items[0].url == "https://canvas.ubc.ca/courses/7/assignments/99"
    assert items[1].url == "https://canvas.ubc.ca/courses/7/calendar_events/55"


def test_identical_generic_urls_no_longer_collide():
    # Before the fix, items 0 and 1 shared the exact same (source, url) -
    # rule 4's identity - so hub.db upserts would have collapsed them into
    # one row.
    items = parse(FEED, source="canvas")
    assert items[0].url != items[1].url


def test_all_day_event_due_is_promoted_to_a_tz_aware_midnight():
    # DTSTART;VALUE=DATE has no time component - icalendar hands back a bare
    # `date`, never a naive datetime here (would crash anything comparing
    # against datetime.now(timezone.utc), e.g. Hide overdue).
    items = parse(FEED, source="canvas")
    due = items[2].due
    assert due.tzinfo is not None
    assert (due.year, due.month, due.day) == (2026, 10, 5)
    assert due.tzinfo == timezone.utc


def test_unrecognized_uid_falls_back_without_crashing():
    items = parse(FEED, source="canvas")
    untagged = items[3]
    assert untagged.course == ""
    assert untagged.title == "Untagged item"
    assert untagged.kind == "assignment"  # no URL either -> the old default guess
    assert untagged.url == ""


def test_no_course_suffix_is_fine():
    # Moodle feeds don't tag "[COURSE]" onto the summary.
    items = parse(FEED, source="moodle")
    assert items[3].course == ""
    assert items[3].source == "moodle"


@pytest.mark.parametrize("url,expected", [
    ("https://canvas.ubc.ca/feeds/calendars/abc.ics", True),
    ("https://ubc.instructure.com/feeds/calendars/abc.ics", True),
    ("https://sub.instructure.com/feeds/calendars/abc.ics", True),
    ("http://canvas.ubc.ca/feeds/calendars/abc.ics", False),  # not https
    ("https://evil.example.com/feeds/calendars/abc.ics", False),  # not on the list
    ("https://notcanvas.ubc.ca.evil.com/x", False),  # lookalike host, not a real suffix match
    ("not a url", False),
])
def test_is_allowed_feed_host(url, expected):
    assert is_allowed_feed_host(url) == expected


def test_is_allowed_feed_host_honours_the_test_only_oracle_env_var(monkeypatch):
    monkeypatch.setenv("FEED_ORACLE_HOST", "canvas.selfhost.test")
    assert is_allowed_feed_host("https://canvas.selfhost.test/feeds/calendars/abc.ics") is True
    assert is_allowed_feed_host("https://canvas.selfhost.test/feeds/calendars/abc.ics".replace("https", "http")) is False


def test_fetch_untrusted_rejects_a_disallowed_host_without_ever_requesting_it(monkeypatch):
    called = []
    monkeypatch.setattr(ics.requests, "get", lambda *a, **k: called.append(1))
    with pytest.raises(ValueError):
        ics.fetch_untrusted("https://evil.example.com/feed.ics", "canvas")
    assert called == []  # never made the request at all


def test_fetch_untrusted_rejects_a_too_large_response(monkeypatch):
    class FakeRaw:
        def read(self, n, decode_content=True):
            return b"x" * (n)  # always "fills" whatever's asked for

    class FakeResponse:
        def raise_for_status(self):
            pass

        raw = FakeRaw()

    monkeypatch.setattr(ics.requests, "get", lambda *a, **k: FakeResponse())
    with pytest.raises(ValueError):
        ics.fetch_untrusted("https://canvas.ubc.ca/feeds/calendars/abc.ics", "canvas")


def test_fetch_untrusted_parses_a_normal_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        class raw:
            @staticmethod
            def read(n, decode_content=True):
                return FEED.encode()

    monkeypatch.setattr(ics.requests, "get", lambda *a, **k: FakeResponse())
    items = ics.fetch_untrusted("https://canvas.ubc.ca/feeds/calendars/abc.ics", "canvas")
    assert len(items) == 4
    assert items[0].source == "canvas"
