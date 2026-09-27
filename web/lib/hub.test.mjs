import { test } from "node:test";
import assert from "node:assert/strict";
import { selectConnections } from "./hub.js";

test("selectConnections: no data means nothing is connected", () => {
  const connections = selectConnections([], []);
  assert.deepEqual(
    connections.map((c) => c.connected),
    [false, false, false],
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
