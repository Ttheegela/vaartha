import type { Bill, RecurringKind } from "./types.ts"

export const WEEKS_PER_MONTH = 52 / 12
const MONTHS_PER_YEAR = 12

type Frequency = Bill["frequency"]
type RecurringLike = { kind: RecurringKind; amount: number; frequency: Frequency; inactive?: boolean }

/** Convert a charge to its average monthly cost. */
export function monthlyCost(amount: number, frequency: Frequency): number {
  if (frequency === "Annual") return amount / MONTHS_PER_YEAR
  if (frequency === "Weekly") return amount * WEEKS_PER_MONTH
  return amount
}

/** Split recurring charges into subscriptions and bills with monthly totals (inactive excluded). */
export function splitRecurring<T extends RecurringLike>(items: T[]) {
  const total = (xs: T[]) =>
    xs.filter((x) => !x.inactive).reduce((sum, x) => sum + monthlyCost(x.amount, x.frequency), 0)
  const subscriptions = items.filter((x) => x.kind === "subscription")
  const bills = items.filter((x) => x.kind === "bill")
  return { subscriptions, bills, subscriptionsMonthly: total(subscriptions), billsMonthly: total(bills) }
}
