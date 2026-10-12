import type { components } from "./api-types.ts"
import type { Account, Bill, Budget, Goal, MerchantSpend } from "./types.ts"

type S = components["schemas"]
type Recurring = S["RecurringOut"]

const FREQUENCY: Record<Recurring["frequency"], Bill["frequency"]> = {
  WEEKLY: "Weekly", MONTHLY: "Monthly", ANNUALLY: "Annual",
}
const PRICE_EPSILON = 0.005
const MONTH_FMT = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" })
const DAY_FMT = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" })

const utc = (iso: string) => new Date(`${iso}T00:00:00Z`)
const sameMonth = (iso: string, today: Date) =>
  iso.slice(0, 7) === `${today.getUTCFullYear()}-${String(today.getUTCMonth() + 1).padStart(2, "0")}`
const cents = (n: number) => Math.round(n * 100) / 100

/** "FOOD_AND_DRINK" -> "Food and drink". */
export function categoryLabel(pfc: string): string {
  const words = pfc.toLowerCase().split("_")
  return words.map((w, i) => (i === 0 ? w[0].toUpperCase() + w.slice(1) : w)).join(" ")
}

export function toAccounts(a: S["AccountsOut"]): Account[] {
  return a.accounts.map((x) => ({
    id: x.account_id, institution: x.institution ?? "Unknown", name: x.name, type: x.subtype ?? x.type,
    mask: x.mask ?? "", balance: x.balance_current ?? 0, liability: x.is_liability,
  }))
}

export function toBills(r: S["RecurringListOut"], today: Date): Bill[] {
  return [...r.subscriptions, ...r.bills].map((s) => {
    const next = sameMonth(s.predicted_next_date, today)
    const last = !next && sameMonth(s.last_date, today)
    const placed = next ? s.predicted_next_date : last ? s.last_date : null
    const diff = s.last_amount - s.avg_amount
    return {
      id: s.stream_id, merchant: s.merchant, amount: s.last_amount,
      day: placed ? utc(placed).getUTCDate() : 0, date: DAY_FMT.format(utc(s.predicted_next_date)), nextDate: s.predicted_next_date,
      frequency: FREQUENCY[s.frequency], kind: s.kind === "bill" ? "bill" : "subscription",
      paid: Boolean(last), inactive: !s.is_active, priceUp: diff > PRICE_EPSILON ? cents(diff) : undefined,
    }
  })
}

export function toBudgets(b: S["BudgetOut"][]): Budget[] {
  return b.map((x) => ({ category: categoryLabel(x.category), spent: x.spent, limit: x.limit }))
}

export function toGoals(g: S["GoalOut"][]): Goal[] {
  return g.map((x) => ({
    name: x.name, current: x.current, target: x.target_amount,
    targetDate: x.target_date ? DAY_FMT.format(utc(x.target_date)) : "No date",
    projectedDate: x.months_left === null ? "—" : `${x.months_left} months left`,
    status: x.progress >= 1 || x.months_left !== 0 ? "On track" : "Behind",
  }))
}

export function toCategorySpend(s: S["SpendingOut"]) {
  return s.by_category.map((c) => ({ name: categoryLabel(c.category), value: cents(c.amount) }))
}

export function toMerchantSpend(s: S["SpendingOut"]): MerchantSpend[] {
  return s.by_merchant.map((m) => ({
    merchant: m.merchant, category: m.category ? categoryLabel(m.category) : "Other",
    amount: cents(m.amount), transactions: m.count,
  }))
}

export function toCashFlow(s: S["SpendingOut"]) {
  return s.cash_flow.map((c) => ({ month: MONTH_FMT.format(utc(`${c.month}-01`)), income: cents(c.income), spend: cents(c.spend) }))
}

/** Last point per month. */
export function toNetWorth(points: S["NetWorthPoint"][]) {
  const byMonth = new Map<string, number>()
  for (const p of points) byMonth.set(p.date.slice(0, 7), p.net)
  return [...byMonth].map(([m, v]) => ({ month: MONTH_FMT.format(utc(`${m}-01`)), value: cents(v) }))
}
