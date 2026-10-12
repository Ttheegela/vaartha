import { test } from "node:test"
import assert from "node:assert/strict"
import { daysInMonth, firstWeekday, upcomingBills } from "../lib/calendar.ts"
import type { Bill } from "../lib/types.ts"

const bill = (id: string, day: number) => ({ id, day }) as Bill

test("month grid math", () => {
  assert.equal(daysInMonth(new Date("2026-02-10T00:00:00Z")), 28)
  assert.equal(daysInMonth(new Date("2028-02-10T00:00:00Z")), 29)
  assert.equal(daysInMonth(new Date("2026-10-31T23:00:00Z")), 31)
  assert.equal(firstWeekday(new Date("2026-11-15T00:00:00Z")), 0) // Nov 1 2026 is a Sunday
  assert.equal(firstWeekday(new Date("2026-10-15T00:00:00Z")), 4) // Oct 1 2026 is a Thursday
})

test("upcomingBills keeps today..today+7, sorted, drops unplaced", () => {
  const out = upcomingBills([bill("a", 20), bill("b", 12), bill("c", 0), bill("d", 19), bill("e", 11), bill("f", 13)], new Date("2026-10-12T12:00:00Z"))
  assert.deepEqual(out.map((b) => b.id), ["b", "f", "d"])
})
