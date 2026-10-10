import test from "node:test";
import assert from "node:assert/strict";
import { newTrainingFailures } from "../src/training-errors.js";

test("report new background failures once, without replaying historical failures", () => {
  const failed = { id: "run-1", status: "failed", error: "CUDA out of memory" };
  assert.deepEqual(newTrainingFailures([failed], null), []);
  assert.deepEqual(newTrainingFailures([failed], new Map([["run-1", "running"]])), [{ jobId: "run-1", message: failed.error }]);
  assert.deepEqual(newTrainingFailures([failed], new Map([["run-1", "failed"]])), []);
  assert.equal(newTrainingFailures([{ id: "run-2", status: "failed" }], new Map())[0].message,
    "The trainer failed without providing an error description.");
});
