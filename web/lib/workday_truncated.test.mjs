// Regression oracle for e3db118, mirrors tests/test_workday_truncated_dimension.py:
// the fixture declares <dimension ref="A1:A1"/> (so SheetJS's !ref is A1:A1)
// but has 8 populated rows; every course must still be parsed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { fixTruncatedRange, parseWorkdayCourses } from "./workday.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.join(here, "..", "..", "fixtures", "workday_truncated_dimension.xlsx");

function load() {
  return parseWorkdayCourses(readFileSync(FIXTURE), "2026W1");
}

test("truncated dimension still parses every row", () => {
  assert.deepEqual(
    load().map((c) => c.code),
    ["FAKE 101", "FAKE 202", "FAKE 303", "FAKE 404"]
  );
});

test("truncated dimension last row fields", () => {
  const courses = load();
  assert.equal(courses.at(-1).title, "Last Row Standing");
  assert.equal(courses.at(-1).term, "2026W1");
});

test("a stray cell at Excel's absolute max address doesn't blow up the recomputed range", () => {
  // A real export was seen with a stray populated cell out at XFD1048576
  // (Excel's literal maximum row/column) - naively trusting every populated
  // address made fixTruncatedRange's recomputed range span ~17 billion
  // cells, which sheet_to_json then tried to materialize and hung on.
  const sheet = { A1: { v: "x" }, B2: { v: "y" }, XFD1048576: { v: "stray" } };
  fixTruncatedRange(sheet);
  assert.equal(sheet["!ref"], "A1:B2"); // bounded by the real B2 cell, XFD1048576 ignored as out of sane range
});
