"""One SQLite file, normalised tables (Terrace's storage proposal, Agent board #15).

`courses` organizes everything; `items` holds every task/deadline/material
from any adapter, tagged by `category` (see hub.models.CATEGORY_FOR).
Textbooks get their own table since they carry ISBN/price, not a due date.

# ponytail: no raw-per-provider tables yet. Add them (one JSON blob table
# per source) only if we actually need to re-normalise without refetching -
# right now every adapter is cheap enough to just re-fetch.
"""
import sqlite3
from pathlib import Path

from hub.logic import normalise_course_code

PATH = Path.home() / ".ubc-hub" / "hub.db"


def _canonical_code(code):
    """"CPSC 121", "CPSC 121 101 2026W1" and "cpsc121" all name the same
    course - collapse every code to "FACULTY NUMBER" (section dropped: it's
    schedule/clash data, not part of course identity) so Canvas's long code
    and Workday's short one land on the same course row. Falls back to the
    raw text when it doesn't parse, rather than silently dropping the
    course."""
    faculty, number, _section = normalise_course_code(code)
    return f"{faculty} {number}" if faculty and number else code

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL,
    term TEXT NOT NULL,
    title TEXT NOT NULL,
    grade REAL,
    UNIQUE(code, term)
);

CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY,
    course_id INTEGER REFERENCES courses(id),
    category TEXT NOT NULL CHECK (category IN ('task', 'deadline', 'material')),
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    due TEXT,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    done INTEGER,  -- NULL = unknown/not applicable; 0/1 otherwise. "overdue"/"soon" are never stored - see hub.models.status_of
    UNIQUE(source, url)
);

CREATE TABLE IF NOT EXISTS textbooks (
    id INTEGER PRIMARY KEY,
    course_id INTEGER REFERENCES courses(id),
    title TEXT NOT NULL,
    isbn TEXT NOT NULL,
    required INTEGER NOT NULL,
    price REAL,
    url TEXT NOT NULL,
    UNIQUE(course_id, isbn)
);
"""


def connect(path=PATH):
    if path != ":memory:":
        path.parent.mkdir(mode=0o700, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    # CREATE TABLE IF NOT EXISTS doesn't add columns to a table that already
    # exists - a hub.db from before `done` landed would crash on it (#27,
    # #21) with "no such column: items.done". Guarded, so this is a no-op
    # once every db has the column.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(items)")}
    if "done" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN done INTEGER")
    return conn


def _course_id(conn, course):
    code = _canonical_code(course.code)
    conn.execute(
        "INSERT INTO courses (code, term, title, grade) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(code, term) DO UPDATE SET title=excluded.title, grade=excluded.grade",
        (code, course.term, course.title, course.grade),
    )
    row = conn.execute("SELECT id FROM courses WHERE code=? AND term=?", (code, course.term)).fetchone()
    return row[0]


def save(conn, courses=(), items=(), textbooks=()):
    """Upsert courses, then items/textbooks matched to them by canonical
    course code (see _canonical_code) - collapses Canvas's long code,
    Workday's short one and PrairieLearn's onto the same course row."""
    ids = {_canonical_code(c.code): _course_id(conn, c) for c in courses}
    for i in items:
        conn.execute(
            "INSERT INTO items (course_id, category, kind, title, due, url, source, done) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source, url) DO UPDATE SET category=excluded.category, kind=excluded.kind, "
            "title=excluded.title, due=excluded.due, done=excluded.done",
            (ids.get(_canonical_code(i.course)), i.category, i.kind, i.title,
             i.due.isoformat() if i.due else None, i.url, i.source,
             None if i.done is None else int(i.done)),
        )
    for t in textbooks:
        cid = ids.get(_canonical_code(t.course))
        if cid is None:
            continue  # no matching course this call; skip rather than orphan the row
        conn.execute(
            "INSERT INTO textbooks (course_id, title, isbn, required, price, url) VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(course_id, isbn) DO UPDATE SET title=excluded.title, required=excluded.required, "
            "price=excluded.price, url=excluded.url",
            (cid, t.title, t.isbn, int(t.required), t.price, t.url),
        )
    conn.commit()


def upcoming(conn, category=None):
    """Items with a due date, soonest first, joined to their course code.
    `category` filters to just "task"/"deadline"/"material" if given.
    Row shape: (code, category, kind, title, due, url, done). `done` is
    0/1/None as stored - build a Status ("overdue"/"soon"/...) from it and
    `due` with hub.models.status_of, don't recompute the logic here.

    LEFT JOIN, not JOIN: an item whose course didn't resolve at save() time
    (e.g. Canvas connected before any course-giving source has run) must
    still show up here - an INNER JOIN would silently vanish it instead of
    just showing an unknown course, and "always produce something useful,
    never refuse on partial data" is this repo's own stated rule."""
    q = ("SELECT COALESCE(courses.code, '(unknown course)'), items.category, items.kind, items.title, "
         "items.due, items.url, items.done "
         "FROM items LEFT JOIN courses ON courses.id = items.course_id "
         "WHERE items.due IS NOT NULL" + (" AND items.category = ?" if category else "") +
         " ORDER BY items.due")
    return conn.execute(q, (category,) if category else ()).fetchall()


def courses(conn):
    """Every course, e.g. for a Courses / Course-card screen."""
    return conn.execute("SELECT code, term, title, grade FROM courses ORDER BY code").fetchall()


def by_course(conn, category=None):
    """upcoming(), grouped under each course code - what a Course card wants:
    "this course's" tasks/deadlines/materials, each list still soonest-first."""
    grouped = {}
    for row in upcoming(conn, category):
        grouped.setdefault(row[0], []).append(row)
    return grouped
