"""Demo frontend: what's due next, across every connected provider."""
from datetime import datetime, timedelta, timezone

import streamlit as st

from hub import canvas, db, prairielearn
from hub.logic import sort_items
from hub.models import Course, Item, category_for, classify_urgency, status_of

st.set_page_config(page_title="UBC Hub")
st.title("UBC Hub")
st.caption("Gotham for students: every provider, one pane of glass.")


def sample_conn():
    """In-memory DB with made-up items, so the demo runs without a Canvas login."""
    # ponytail: rebuilt every rerun (it's tiny). Swap for fixtures/ once Vihaan's land on main.
    now = datetime.now(timezone.utc)
    rows = [("CPSC 121", "Problem Set 3", "assignment", 2), ("CPSC 121", "Quiz 2", "quiz", 4),
            ("MATH 100", "Midterm 1", "exam", 9), ("ENGL 110", "Read ch. 4", "reading", 1),
            ("MATH 100", "WeBWorK 3", "assignment", -1)]
    courses = [Course(code=c, section="101", term="2026W1", title=c) for c in {r[0] for r in rows}]
    items = [Item(course=c, category=category_for(k), kind=k, title=t, due=now + timedelta(days=d),
                  url=f"https://example.invalid/{n}", source="sample") for n, (c, t, k, d) in enumerate(rows)]
    conn = db.connect(":memory:")
    db.save(conn, courses, items)
    return conn


with st.sidebar:
    demo = st.toggle("Sample data", value=True, help="Off = your own Canvas data from this laptop's hub.db")
    if not demo:
        col1, col2 = st.columns(2)
        if col1.button("Connect Canvas", help="Opens a browser window: sign in with CWL + Duo yourself"):
            with st.spinner("Waiting for you to sign in to Canvas…"):
                db.save(db.connect(), *canvas.fetch())
        if col2.button("Connect PrairieLearn", help="Opens a browser window: sign in with CWL + Duo yourself"):
            with st.spinner("Waiting for you to sign in to PrairieLearn…"):
                db.save(db.connect(), *prairielearn.fetch())
    n = st.slider("Show next", 5, 50, 10)
    hide_overdue = st.toggle("Hide overdue", value=False)

conn = sample_conn() if demo else db.connect()
now = datetime.now(timezone.utc)

for tab, category in zip(st.tabs(["All", "Tasks", "Deadlines", "Materials"]), [None, "task", "deadline", "material"]):
    with tab:
        def status(r):
            item = Item(course=r[0], category=r[1], kind=r[2], title=r[3],
                        due=datetime.fromisoformat(r[4]), url=r[5], source="", done=bool(r[6]) if r[6] is not None else None)
            return status_of(item, now)

        # Completed items never show, regardless of the Hide overdue toggle -
        # nothing left to do about them.
        rows = [r for r in db.upcoming(conn, category)
                if status(r) != "done" and (not hide_overdue or status(r) != "overdue")]
        rows = sort_items(rows, now)[:n]
        if not rows:
            st.info("Nothing upcoming." if demo else "Nothing yet. Connect Canvas in the sidebar.")
            continue
        st.dataframe(
            [{"Urgency": classify_urgency(r[3], datetime.fromisoformat(r[4]), now).capitalize(),
              "Due": datetime.fromisoformat(r[4]).astimezone(), "Course": r[0], "What": r[3], "Kind": r[2], "Link": r[5]}
             for r in rows],
            column_config={"Due": st.column_config.DatetimeColumn(format="ddd MMM D, h:mm a"),
                           "Link": st.column_config.LinkColumn(display_text="open")},
            hide_index=True, use_container_width=True,
        )
