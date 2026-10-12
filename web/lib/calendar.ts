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

/** Bills falling today through the next 7 days of this month, by day. Day 0 (unplaced) is excluded. */
export function upcomingBills(bills: Bill[], today: Date): Bill[] {
  const t = today.getUTCDate()
  return bills.filter((b) => b.day >= t && b.day <= t + UPCOMING_DAYS).sort((a, b) => a.day - b.day)
}
