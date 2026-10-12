import { test } from "node:test"
import assert from "node:assert/strict"
import { daysInMonth, firstWeekday, upcomingBills } from "../lib/calendar.ts"
import type { Bill } from "../lib/types.ts"

test("month grid math", () => {
  assert.equal(daysInMonth(new Date("2026-02-10T00:00:00Z")), 28)
  assert.equal(daysInMonth(new Date("2028-02-10T00:00:00Z")), 29)
  assert.equal(daysInMonth(new Date("2026-10-31T23:00:00Z")), 31)
  assert.equal(firstWeekday(new Date("2026-11-15T00:00:00Z")), 0) // Nov 1 2026 is a Sunday
  assert.equal(firstWeekday(new Date("2026-10-15T00:00:00Z")), 4) // Oct 1 2026 is a Thursday
})

const bill = (id: string, nextDate: string, inactive = false) => ({ id, nextDate, inactive }) as Bill
const ids = (bs: Bill[]) => bs.map((b) => b.id)

test("upcomingBills crosses month boundary, sorted", () => {
  const today = new Date("2026-10-28T12:00:00Z")
  assert.deepEqual(ids(upcomingBills([bill("late", "2026-11-04"), bill("rent", "2026-11-01"), bill("now", "2026-10-28")], today)), ["now", "rent", "late"])
})

test("upcomingBills excludes beyond 7 days, inactive, and past", () => {
  const today = new Date("2026-10-28T12:00:00Z")
  assert.deepEqual(ids(upcomingBills([bill("far", "2026-11-06"), bill("off", "2026-10-30", true), bill("past", "2026-10-27")], today)), [])
})
