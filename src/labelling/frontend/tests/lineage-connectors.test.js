import test from "node:test";
import assert from "node:assert/strict";
import { connectionArrowhead, connectionLabel, connectionPath } from "../src/lineage-connectors.js";

test("connectors point into the actual destination, including within one column", () => {
  const source = { x: 0, y: 0, width: 100, height: 80 };
  assert.equal(connectionPath(source, { x: 160, y: 100, width: 100, height: 80 }), "M 101 40 C 128 40, 128 140, 155 140");
  assert.equal(connectionPath(source, { ...source, y: 160 }), "M -1 40 C -37 40, -37 200, -5 200");
  assert.equal(connectionPath(source, { ...source, y: 108 }), "M 50 81 C 50 89, 50 95, 50 103");
  assert.equal(connectionArrowhead({ ...source, y: 108 }, source), "M 50 103 L 46 95 L 54 95 Z");
  assert.equal(connectionArrowhead({ x: 160, y: 100, width: 100, height: 80 }), "M 155 140 L 147 136 L 147 144 Z");
  assert.equal(connectionLabel({ type: "training" }, { type: "model" }), "Trained model published");
  assert.equal(connectionLabel({ type: "version" }, { type: "training" }), "Used dataset for training");
  assert.match(connectionLabel({ type: "lakefs" }, { type: "training" }, "snapshot"), /snapshot/);
});
