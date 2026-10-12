import type { Bill } from "./types.ts"

const UPCOMING_DAYS = 7

/** Days in the UTC month of `d`. */
export function daysInMonth(d: Date): number {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()
}

/** Weekday (0 = Sunday) of the 1st of the UTC month of `d`. */
export function firstWeekday(d: Date): number {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1)).getUTCDay()
}

const DAY_MS = 86_400_000

/** Active bills whose next date is within [today, today+7 days] (UTC, any month), soonest first. */
export function upcomingBills(bills: Bill[], today: Date): Bill[] {
  const start = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate())
  const end = start + UPCOMING_DAYS * DAY_MS
  const at = (b: Bill) => Date.parse(`${b.nextDate}T00:00:00Z`)
  return bills.filter((b) => !b.inactive && at(b) >= start && at(b) <= end).sort((a, b) => at(a) - at(b))
}
