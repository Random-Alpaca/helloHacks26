"""hub/demo.py: the fake demo student, through the real adapters + fusion."""
import socket
from datetime import datetime, timezone

import pytest
import requests

from hub import demo

# Fixed "now" so the test doesn't depend on today (the UBC key dates are real
# calendar dates; fixture offsets move with `now`).
NOW = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("hub.demo must not touch the network")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)
    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests, "post", refuse)


def test_rows_come_from_at_least_three_real_providers():
    out = demo.demo_rows(NOW)
    assert out["demo"] is True
    assert {"canvas", "prairielearn", "ubc_key_dates"} <= {r["source"] for r in out["items"]}


def test_every_due_is_tz_aware_or_none():
    out = demo.demo_rows(NOW)
    for r in out["items"] + out["announcements"]:
        if r["due"] is not None:
            assert datetime.fromisoformat(r["due"]).tzinfo is not None, r


def test_cross_source_duplicate_is_fused():
    # The raw adapters really do see the quiz twice (Canvas + PrairieLearn)...
    _, raw = demo._gather(NOW)
    assert {i.source for i in raw if i.title == "Quiz 3: Recursion"} == {"canvas", "prairielearn"}
    # ...and the Canvas API + Canvas calendar feed both carry Problem Set 4.
    assert sum(i.title == "Problem Set 4" for i in raw) == 2
    out = demo.demo_rows(NOW)
    assert sum(r["title"] == "Quiz 3: Recursion" for r in out["items"]) == 1
    assert sum(r["title"] == "Problem Set 4" for r in out["items"]) == 1


def test_source_url_identity_is_unique():
    out = demo.demo_rows(NOW)
    rows = out["items"] + out["announcements"]
    keys = [(r["source"], r["url"]) for r in rows]
    assert len(keys) == len(set(keys))


def test_done_items_are_hidden_and_rows_are_ranked():
    out = demo.demo_rows(NOW)
    titles = [r["title"] for r in out["items"]]
    assert "Reading response 3" not in titles  # submitted on Canvas
    assert "HW 4: Lists" not in titles  # 100% on PrairieLearn
    assert out["items"][0]["status"] == "overdue"


def test_dates_are_relative_to_now():
    # Problem Set 4 is stored as "{{due:+1d@23:59}}": tomorrow, 23:59 Vancouver
    # time, whenever the request happens (a wall-clock check, since DST moves
    # the UTC offset between the two dates).
    for now in (NOW, NOW.replace(month=11), NOW.replace(year=2027, month=3)):
        row = next(r for r in demo.demo_rows(now)["items"] if r["title"] == "Problem Set 4")
        due = datetime.fromisoformat(row["due"]).astimezone(demo.VAN)
        assert (due.date() - now.astimezone(demo.VAN).date()).days == 1
        assert (due.hour, due.minute) == (23, 59)


def test_courses_are_fused_across_providers():
    by_code = {c["code"]: c for c in demo.demo_rows(NOW)["courses"]}
    assert by_code["CPSC 110"]["grade"] == 86.4  # Canvas grade on a Workday course
    assert by_code["CPSC 110"]["title"] == "Intro to Program Design (Demo)"
    assert "PSYC 102" in by_code  # Workday-only course still shows
