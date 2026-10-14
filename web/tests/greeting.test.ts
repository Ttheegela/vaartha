import { test } from "node:test"
import assert from "node:assert/strict"
import { greeting, todayLabel } from "../lib/greeting.ts"

const NY = "America/New_York"
// 2026-10-14T03:05Z is 23:05 on Oct 13 in New York
const lateNight = new Date("2026-10-14T03:05:00Z")

test("greeting follows the local hour, not UTC", () => {
  assert.equal(greeting(lateNight, NY), "Good evening")
  assert.equal(greeting(new Date("2026-10-13T13:00:00Z"), NY), "Good morning")
  assert.equal(greeting(new Date("2026-10-13T18:00:00Z"), NY), "Good afternoon")
  assert.equal(greeting(new Date("2026-10-13T08:30:00Z"), NY), "Good evening") // 04:30 local
})

test("todayLabel uses the local date", () => {
  assert.equal(todayLabel(lateNight, NY), "TUESDAY, OCTOBER 13")
})
