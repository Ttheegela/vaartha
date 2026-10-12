import { test } from "node:test"
import assert from "node:assert/strict"
import { relativeTime } from "../lib/relative-time.ts"

const now = new Date("2026-10-12T12:00:00Z")
test("relativeTime", () => {
  assert.equal(relativeTime(null, now), "Never")
  assert.equal(relativeTime("2026-10-12T11:59:40Z", now), "just now")
  assert.equal(relativeTime("2026-10-12T10:00:00Z", now), "2 hours ago")
  assert.equal(relativeTime("2026-10-10T12:00:00Z", now), "2 days ago")
})
