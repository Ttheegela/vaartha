const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [["day", 86400], ["hour", 3600], ["minute", 60]]
const RTF = new Intl.RelativeTimeFormat("en", { numeric: "auto" })

/** "2 hours ago"-style text for an ISO timestamp; "Never" when null/invalid. */
export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  const t = iso ? Date.parse(iso) : NaN
  if (Number.isNaN(t)) return "Never"
  const secs = Math.round((t - now.getTime()) / 1000)
  for (const [unit, size] of UNITS) if (Math.abs(secs) >= size) return RTF.format(Math.trunc(secs / size), unit)
  return "just now"
}
