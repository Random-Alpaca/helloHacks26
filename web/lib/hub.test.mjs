import { test } from "node:test";
import assert from "node:assert/strict";
import { hideCourseItems, selectConnections, selectVisibleCourses } from "./hub.js";

test("selectConnections: no data means nothing is connected", () => {
  const connections = selectConnections([], []);
  assert.deepEqual(
    connections.map((c) => c.connected),
    [false, false, false, false],
  );
});

test("selectConnections: source-tagged items mark that provider connected, others untouched", () => {
  const items = [
    { source: "canvas" },
    { source: "canvas" },
    { source: undefined }, // sample data - never counts toward a real connection
  ];
  const connections = selectConnections(items, []);
  const byId = Object.fromEntries(connections.map((c) => [c.id, c]));
  assert.equal(byId.canvas.connected, true);
  assert.equal(byId.canvas.detail, "2 items");
  assert.equal(byId.prairielearn.connected, false);
  assert.equal(byId.workday.connected, false);
});

test("selectConnections: imported Workday courses count as connected regardless of items", () => {
  const connections = selectConnections([], [{ code: "BMEG 201" }]);
  const workday = connections.find((c) => c.id === "workday");
  assert.equal(workday.connected, true);
  assert.equal(workday.detail, "1 course imported");
});

test("selectConnections: an unrecognized source shows up as its own custom PrairieLearn row", () => {
  // Any source that isn't one of the known providers is a PrairieLearn
  // instance a student pasted in directly (resolve_campus() accepts a full
  // URL for any self-hosted instance we don't have a fixed entry for).
  const items = [{ source: "pl.autoed.ok.ubc.ca" }, { source: "pl.autoed.ok.ubc.ca" }];
  const connections = selectConnections(items, []);
  const custom = connections.find((c) => c.id === "pl.autoed.ok.ubc.ca");
  assert.ok(custom, "custom source should get its own row");
  assert.equal(custom.connected, true);
  assert.equal(custom.detail, "2 items");
  // and it shouldn't duplicate or displace the known providers
  assert.equal(connections.filter((c) => c.id === "prairielearn").length, 1);
});

test("selectVisibleCourses: drops hidden courses, keeps everything else", () => {
  const courses = [{ code: "CPSC 121" }, { code: "OLD 100" }, { code: "MATH 100" }];
  assert.deepEqual(
    selectVisibleCourses(courses, ["OLD 100"]).map((c) => c.code),
    ["CPSC 121", "MATH 100"],
  );
  assert.deepEqual(selectVisibleCourses(courses, []).map((c) => c.code), ["CPSC 121", "OLD 100", "MATH 100"]);
});

test("hideCourseItems: drops items belonging to a hidden course", () => {
  const items = [{ course: "CPSC 121" }, { course: "OLD 100" }];
  assert.deepEqual(hideCourseItems(items, ["OLD 100"]).map((i) => i.course), ["CPSC 121"]);
});
