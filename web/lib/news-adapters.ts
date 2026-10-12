import type { components } from "./api-types.ts"
import { relativeTime } from "./relative-time.ts"
import type { NewsItem } from "./types.ts"

type S = components["schemas"]

export interface LiveNewsItem extends NewsItem { url: string | null }

const SENTIMENT_THRESHOLD = 0.15
const MATERIAL_THRESHOLD = 0.3
const HTTP_URL = /^https?:\/\//i
const SOURCE_PREFIX = /^(Alpaca|Finnhub|GDELT)\//

/** Maps API news to UI items using the first ticker's score (else first score); unscored -> neutral. */
export function toNewsItems(items: S["NewsItemOut"][], now: Date): LiveNewsItem[] {
  return items.map((n) => {
    const s = n.scores.find((x) => x.ticker === n.tickers[0]) ?? n.scores[0]
    const v = s?.sentiment ?? 0
    return {
      id: String(n.id),
      source: n.source.replace(SOURCE_PREFIX, ""),
      time: relativeTime(n.published_at, now),
      title: n.title,
      tickers: n.tickers,
      sentiment: v > SENTIMENT_THRESHOLD ? "positive" : v < -SENTIMENT_THRESHOLD ? "negative" : "neutral",
      stress: s?.stress ?? "none",
      event: s?.event ?? "",
      material: (s?.material ?? 0) >= MATERIAL_THRESHOLD,
      url: n.url && HTTP_URL.test(n.url) ? n.url : null,
    }
  })
}

/** Maps Polymarket rows to the sidebar shape (whole-percent probability). */
export function toCrowdOdds(m: S["CrowdOddsOut"][]): { question: string; probability: number }[] {
  return m.map((x) => ({ question: x.question, probability: Math.round(x.yes_prob * 100) }))
}
