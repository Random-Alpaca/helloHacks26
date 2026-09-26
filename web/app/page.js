"use client";

import { useState } from "react";

// Same category buckets as hub/models.py's CATEGORY_FOR on main.
const CATEGORY_FOR = {
  assignment: "task",
  announcement: "task",
  quiz: "deadline",
  exam: "deadline",
  event: "deadline",
  break: "deadline",
  payment: "deadline",
  reading: "material",
  textbook: "material",
};

// Same 5 made-up rows as app.py's sample_conn(), so the two demos match.
const SAMPLE_ROWS = [
  { course: "CPSC 121", title: "Problem Set 3", kind: "assignment", dueInDays: 2 },
  { course: "CPSC 121", title: "Quiz 2", kind: "quiz", dueInDays: 4 },
  { course: "MATH 100", title: "Midterm 1", kind: "exam", dueInDays: 9 },
  { course: "ENGL 110", title: "Read ch. 4", kind: "reading", dueInDays: 1 },
  { course: "MATH 100", title: "WeBWorK 3", kind: "assignment", dueInDays: -1 },
];

const TABS = [
  { key: "all", label: "All" },
  { key: "task", label: "Tasks" },
  { key: "deadline", label: "Deadlines" },
  { key: "material", label: "Materials" },
];

function formatDue(date) {
  return date.toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function Page() {
  const [tab, setTab] = useState("all");
  const [hideOverdue, setHideOverdue] = useState(false);

  const now = new Date();
  const items = SAMPLE_ROWS.map((row, i) => ({
    ...row,
    id: i,
    category: CATEGORY_FOR[row.kind] ?? "task",
    due: new Date(now.getTime() + row.dueInDays * 24 * 60 * 60 * 1000),
    url: `https://example.invalid/${i}`,
  }));

  const visible = items
    .filter((item) => tab === "all" || item.category === tab)
    .filter((item) => !hideOverdue || item.due >= now)
    .sort((a, b) => a.due - b.due);

  return (
    <main>
      <h1>UBC Hub</h1>
      <p className="caption">
        Gotham for students: every provider, one pane of glass. (Sample data —
        the live Canvas/PrairieLearn demo runs on a laptop.)
      </p>

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={tab === t.key ? "active" : ""}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <label className="toggle">
        <input
          type="checkbox"
          checked={hideOverdue}
          onChange={(e) => setHideOverdue(e.target.checked)}
        />{" "}
        Hide overdue
      </label>

      {visible.length === 0 ? (
        <p className="empty">Nothing upcoming.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Due</th>
              <th>Course</th>
              <th>What</th>
              <th>Kind</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => (
              <tr key={item.id} className={item.due < now ? "overdue" : ""}>
                <td>{formatDue(item.due)}</td>
                <td>{item.course}</td>
                <td>{item.title}</td>
                <td>{item.kind}</td>
                <td>
                  <a href={item.url}>open</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
