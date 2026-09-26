from datetime import datetime

from hub import db
from hub.models import Course, Item, Textbook

COURSE = Course(code="CPSC 121", section="", term="2026W1", title="Models of Computation", grade=88.5)
QUIZ = Item(course="CPSC 121", category="deadline", kind="quiz", title="Quiz 2",
            due=datetime(2026, 9, 30, 6, 59), url="https://x/q/1", source="canvas")
BOOK = Textbook(course="CPSC 121", title="Discrete Math", isbn="123", required=True, price=80.0, url="https://x/b/1")


def test_save_and_upcoming():
    conn = db.connect(":memory:")
    db.save(conn, [COURSE], [QUIZ], [BOOK])
    rows = db.upcoming(conn)
    assert rows == [("CPSC 121", "deadline", "quiz", "Quiz 2", "2026-09-30T06:59:00", "https://x/q/1")]
    assert conn.execute("SELECT isbn FROM textbooks").fetchall() == [("123",)]


def test_save_is_idempotent_and_updates():
    conn = db.connect(":memory:")
    db.save(conn, [COURSE], [QUIZ])
    updated = Item(**{**QUIZ.__dict__, "title": "Quiz 2 (rescheduled)"})
    db.save(conn, [COURSE], [updated])
    rows = db.upcoming(conn)
    assert len(rows) == 1  # same (source, url) -> updated in place, not duplicated
    assert rows[0][3] == "Quiz 2 (rescheduled)"


def test_upcoming_filters_by_category():
    conn = db.connect(":memory:")
    reading = Item(course="CPSC 121", category="material", kind="reading", title="Ch. 3",
                    due=datetime(2026, 9, 29), url="https://x/r/1", source="canvas")
    db.save(conn, [COURSE], [QUIZ, reading])
    assert [r[2] for r in db.upcoming(conn, category="deadline")] == ["quiz"]
    assert [r[2] for r in db.upcoming(conn, category="material")] == ["reading"]
