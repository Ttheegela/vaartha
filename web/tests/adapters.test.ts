import { test } from "node:test"
import assert from "node:assert/strict"
import { categoryLabel, toAccounts, toBills, toBudgets, toCashFlow, toGoals, toNetWorth } from "../lib/adapters.ts"

const TODAY = new Date("2026-10-12T12:00:00Z")
const stream = (o: Record<string, unknown>) => ({
  stream_id: "s", merchant: "Netflix", kind: "subscription", frequency: "MONTHLY",
  avg_amount: 22.99, last_amount: 22.99, last_date: "2026-09-15", predicted_next_date: "2026-10-15",
  is_active: true, monthly_amount: 22.99, ...o,
})

test("categoryLabel", () => {
  assert.equal(categoryLabel("FOOD_AND_DRINK"), "Food and drink")
  assert.equal(categoryLabel("RENT_AND_UTILITIES"), "Rent and utilities")
})

test("toBills maps frequency, price change, placement", () => {
  const bills = toBills({
    subscriptions: [
      stream({ avg_amount: 21.49, last_amount: 22.99 }),
      stream({ stream_id: "p", merchant: "Prime", frequency: "ANNUALLY", last_date: "2026-10-02",
               predicted_next_date: "2027-10-02", last_amount: 139, avg_amount: 139 }),
      stream({ stream_id: "x", merchant: "Old", is_active: false, last_date: "2026-06-05",
               predicted_next_date: "2026-07-05" }),
    ],
    bills: [stream({ stream_id: "r", merchant: "Rent", kind: "bill", last_amount: 2450, avg_amount: 2450,
                     last_date: "2026-10-01", predicted_next_date: "2026-11-01" })],
    subscriptions_monthly: 0, bills_monthly: 0,
  } as never, TODAY)
  const by = Object.fromEntries(bills.map((b) => [b.merchant, b]))
  assert.equal(by.Netflix.day, 15); assert.equal(by.Netflix.paid, false)
  assert.equal(by.Netflix.priceUp, 1.5); assert.equal(by.Netflix.date, "Oct 15"); assert.equal(by.Netflix.nextDate, "2026-10-15")
  assert.equal(by.Prime.frequency, "Annual"); assert.equal(by.Prime.day, 2); assert.equal(by.Prime.paid, true)
  assert.equal(by.Old.inactive, true); assert.equal(by.Old.day, 0)
  assert.equal(by.Rent.kind, "bill"); assert.equal(by.Rent.day, 1); assert.equal(by.Rent.paid, true)
})

test("empty inputs give empty outputs", () => {
  assert.deepEqual(toAccounts({ accounts: [], items: [], assets: 0, liabilities: 0 }), [])
  assert.deepEqual(toBills({ subscriptions: [], bills: [], subscriptions_monthly: 0, bills_monthly: 0 }, TODAY), [])
  assert.deepEqual(toBudgets([]), [])
  assert.deepEqual(toGoals([]), [])
  assert.deepEqual(toNetWorth([]), [])
})

test("toAccounts marks liabilities and masks", () => {
  const [a] = toAccounts({ accounts: [{ account_id: "c", institution: "Bank", name: "Card", type: "credit",
    subtype: "credit card", mask: "9012", balance_current: 1240.55, balance_available: null, is_liability: true }],
    items: [], assets: 0, liabilities: 1240.55 })
  assert.equal(a.institution, "Bank"); assert.equal(a.mask, "9012"); assert.equal(a.liability, true)
  assert.equal(a.balance, 1240.55)
})

test("toBudgets and toGoals", () => {
  assert.deepEqual(toBudgets([{ category: "FOOD_AND_DRINK", limit: 600, spent: 492 }]),
    [{ category: "Food and drink", spent: 492, limit: 600 }])
  const [g] = toGoals([{ id: 1, name: "Emergency fund", target_amount: 25000, target_date: "2027-06-30",
    current: 18000, progress: 0.72, months_left: 8 }])
  assert.equal(g.current, 18000); assert.equal(g.target, 25000); assert.equal(g.name, "Emergency fund")
})

test("toNetWorth keeps last point per month", () => {
  const pts = toNetWorth([
    { date: "2026-09-01", assets: 10, liabilities: 1, net: 9 },
    { date: "2026-09-30", assets: 12, liabilities: 1, net: 11 },
    { date: "2026-10-12", assets: 15, liabilities: 2, net: 13 },
  ])
  assert.deepEqual(pts.map((p) => p.value), [11, 13])
})

test("toCashFlow month labels", () => {
  const cf = toCashFlow({ month: "2026-10", by_category: [], by_merchant: [],
    cash_flow: [{ month: "2026-09", income: 8240, spend: 5126 }, { month: "2026-10", income: 4120, spend: 900 }] })
  assert.deepEqual(cf.map((c) => c.month), ["Sep", "Oct"])
})
