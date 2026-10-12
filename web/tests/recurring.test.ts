import { test } from "node:test"
import assert from "node:assert/strict"
import { WEEKS_PER_MONTH, monthlyCost, splitRecurring } from "../lib/recurring.ts"

test("monthlyCost normalizes frequencies", () => {
  assert.equal(monthlyCost(12, "Monthly"), 12)
  assert.equal(monthlyCost(120, "Annual"), 10)
  assert.ok(Math.abs(monthlyCost(10, "Weekly") - 10 * WEEKS_PER_MONTH) < 1e-9)
})

test("splitRecurring keeps bills out of the subscription total", () => {
  const items = [
    { kind: "bill" as const, amount: 2450, frequency: "Monthly" as const },
    { kind: "subscription" as const, amount: 11.99, frequency: "Monthly" as const },
    { kind: "subscription" as const, amount: 139, frequency: "Annual" as const },
    { kind: "subscription" as const, amount: 7.99, frequency: "Monthly" as const, inactive: true },
  ]
  const r = splitRecurring(items)
  assert.equal(r.bills.length, 1)
  assert.equal(r.subscriptions.length, 3)
  assert.ok(Math.abs(r.subscriptionsMonthly - (11.99 + 139 / 12)) < 1e-9)
  assert.equal(r.billsMonthly, 2450)
})
