import test from "node:test";
import assert from "node:assert/strict";
import { formatDate } from "../src/dates.js";

test("server dates support SQLite UTC, ISO UTC, and explicit offsets", () => {
  const expected = new Date("2026-10-10T10:30:00Z").toLocaleString();
  for (const value of ["2026-10-10 10:30:00", "2026-10-10T10:30:00Z", "2026-10-10T10:30:00+00:00", "2026-10-10T12:30:00+02:00"]) {
    assert.equal(formatDate(value), expected);
  }
  assert.equal(formatDate(undefined), "Date unavailable");
  assert.equal(formatDate("invalid"), "Date unavailable");
});
