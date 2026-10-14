export const DEFAULT_TZ = "America/New_York"
const MORNING_FROM = 5
const AFTERNOON_FROM = 12
const EVENING_FROM = 17

/** "Good morning/afternoon/evening" for the wall-clock hour in `tz`. */
export function greeting(now: Date, tz: string = DEFAULT_TZ): string {
  const hour = Number(new Intl.DateTimeFormat("en-US", { hour: "numeric", hourCycle: "h23", timeZone: tz }).format(now))
  if (hour >= MORNING_FROM && hour < AFTERNOON_FROM) return "Good morning"
  if (hour >= AFTERNOON_FROM && hour < EVENING_FROM) return "Good afternoon"
  return "Good evening"
}

/** Upper-cased "WEEKDAY, MONTH DAY" for the date in `tz`. */
export function todayLabel(now: Date, tz: string = DEFAULT_TZ): string {
  return new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: tz }).format(now).toUpperCase()
}
