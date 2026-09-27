import functools
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer

from hub import db
from hub.api import ALLOWED_ORIGIN, Handler, _announcements, _upcoming
from hub.models import Course, Item

NOW = datetime.now(timezone.utc)
COURSE = Course(code="CPSC 121", section="", term="2026W1", title="Models of Computation")


def test_done_items_are_excluded_regardless_of_due_date():
    conn = db.connect(":memory:")
    done = Item(course="CPSC 121", category="task", kind="assignment", title="PS2",
                due=NOW - timedelta(days=1), url="https://x/1", source="canvas", done=True)
    db.save(conn, [COURSE], [done])
    assert _upcoming(conn) == []


def test_rows_carry_status_and_urgency():
    conn = db.connect(":memory:")
    overdue = Item(course="CPSC 121", category="task", kind="assignment", title="Final project",
                   due=NOW - timedelta(hours=1), url="https://x/2", source="canvas")
    db.save(conn, [COURSE], [overdue])
    rows = _upcoming(conn)
    assert len(rows) == 1
    assert rows[0]["status"] == "overdue"
    assert rows[0]["urgency"] in ("overdue", "critical", "high", "medium", "low")


def test_sorted_most_urgent_first():
    conn = db.connect(":memory:")
    quiet = Item(course="CPSC 121", category="material", kind="reading", title="Read ch. 4",
                 due=NOW + timedelta(hours=2), url="https://x/3", source="canvas")
    urgent = Item(course="CPSC 121", category="task", kind="exam", title="Final exam",
                  due=NOW + timedelta(hours=2), url="https://x/4", source="canvas")
    db.save(conn, [COURSE], [quiet, urgent])
    rows = _upcoming(conn)
    assert rows[0]["title"] == "Final exam"


def test_announcements_excludes_undated_items_that_are_not_announcements():
    # An undated Canvas assignment (hub/canvas.py's to_undated_item, #43) or
    # an unopened PrairieLearn assessment has no due date either, and used to
    # leak into this feed looking like an announcement.
    conn = db.connect(":memory:")
    announcement = Item(course="CPSC 121", category="task", kind="announcement", title="Welcome!",
                         due=None, url="https://x/a", source="canvas")
    undated_assignment = Item(course="CPSC 121", category="task", kind="assignment", title="Reading response",
                               due=None, url="https://x/b", source="canvas")
    db.save(conn, [COURSE], [announcement, undated_assignment])
    assert [r["title"] for r in _announcements(conn)] == ["Welcome!"]


def _running_server(tmp_path, monkeypatch):
    # These spin up the real server, which calls db.connect() with no args -
    # redirect that to a throwaway file so a CORS test never touches a real
    # ~/.ubc-hub/hub.db.
    monkeypatch.setattr(db, "connect", functools.partial(db.connect, tmp_path / "hub.db"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_cors_allows_the_web_dev_origin(tmp_path, monkeypatch):
    server = _running_server(tmp_path, monkeypatch)
    try:
        port = server.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/courses", headers={"Origin": ALLOWED_ORIGIN})
        with urllib.request.urlopen(req) as res:
            assert res.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
    finally:
        server.shutdown()


def test_cors_rejects_other_origins(tmp_path, monkeypatch):
    server = _running_server(tmp_path, monkeypatch)
    try:
        port = server.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/courses", headers={"Origin": "http://evil.example"})
        with urllib.request.urlopen(req) as res:
            assert res.headers.get("Access-Control-Allow-Origin") is None
    finally:
        server.shutdown()


def test_options_preflight(tmp_path, monkeypatch):
    server = _running_server(tmp_path, monkeypatch)
    try:
        port = server.server_address[1]
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/connect/canvas", method="OPTIONS",
                                      headers={"Origin": ALLOWED_ORIGIN})
        with urllib.request.urlopen(req) as res:
            assert res.status == 204
            assert res.headers["Access-Control-Allow-Origin"] == ALLOWED_ORIGIN
            assert "POST" in res.headers["Access-Control-Allow-Methods"]
    finally:
        server.shutdown()
