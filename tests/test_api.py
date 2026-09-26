from datetime import datetime, timedelta, timezone

from hub import db
from hub.api import _upcoming
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
