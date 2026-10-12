import test from "node:test";
import assert from "node:assert/strict";
import { elapsedTime, heartbeatText } from "../src/training-status.js";

test("durations survive reload and finish at the recorded completion time", () => {
  const now = Date.parse("2026-10-12T12:01:30Z");
  const job = { status: "running", started_at: "2026-10-12T12:00:00+00:00", heartbeat_at: "2026-10-12T12:01:25Z" };
  assert.equal(elapsedTime(job, now), "1m 30s");
  assert.equal(heartbeatText(job, now), "5s ago");
  assert.equal(heartbeatText(job, now + 20000), "25s ago · delayed");
  assert.equal(elapsedTime({ ...job, completed_at: "2026-10-12T12:01:00Z" }, now), "1m 0s");
  assert.equal(elapsedTime({ status: "queued" }, now), "Not started");
  assert.equal(heartbeatText({ status: "succeeded" }, now), "Finished");
});
