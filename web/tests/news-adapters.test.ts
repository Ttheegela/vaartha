import { test } from "node:test"
import assert from "node:assert/strict"
import { toCrowdOdds, toHoldings, toNewsItems, toSentimentSeries } from "../lib/news-adapters.ts"

const NOW = new Date("2026-10-12T12:00:00Z")
const score = (o: Record<string, unknown>) => ({
  ticker: "NVDA", sentiment: 0, sentiment_conf: 0.9, material: 0.5, stress: "none", event: "earnings", noise: 0, scored_by: "llm", ...o,
})
const item = (o: Record<string, unknown>) => ({
  id: 1, published_at: "2026-10-12T09:00:00Z", source: "Alpaca/benzinga", url: "https://x.test/a", title: "T", tickers: ["NVDA"], topics: [], scores: [score({})], ...o,
}) as never

test("empty -> []", () => {
  assert.deepEqual(toNewsItems([], NOW), [])
  assert.deepEqual(toCrowdOdds([]), [])
})

test("sentiment bucket thresholds at +/-0.15 are exclusive", () => {
  const s = (v: number) => toNewsItems([item({ scores: [score({ sentiment: v })] })], NOW)[0].sentiment
  assert.equal(s(0.16), "positive")
  assert.equal(s(0.15), "neutral")
  assert.equal(s(-0.15), "neutral")
  assert.equal(s(-0.16), "negative")
})

test("source prefixes stripped, others kept", () => {
  const src = (v: string) => toNewsItems([item({ source: v })], NOW)[0].source
  assert.equal(src("Alpaca/benzinga"), "benzinga")
  assert.equal(src("Finnhub/Reuters"), "Reuters")
  assert.equal(src("GDELT/ft.com"), "ft.com")
  assert.equal(src("MarketWatch"), "MarketWatch")
  assert.equal(src("SEC EDGAR"), "SEC EDGAR")
})

test("primary score is first ticker's, else first score; material >= 0.3", () => {
  const scores = [score({ ticker: "AMD", sentiment: -0.9, material: 0.1 }), score({ ticker: "NVDA", sentiment: 0.9, material: 0.3, stress: "sector", event: "guidance" })]
  const [a] = toNewsItems([item({ tickers: ["NVDA"], scores })], NOW)
  assert.equal(a.sentiment, "positive")
  assert.equal(a.material, true)
  assert.equal(a.stress, "sector")
  assert.equal(a.event, "guidance")
  const [b] = toNewsItems([item({ tickers: ["TSM"], scores })], NOW)
  assert.equal(b.sentiment, "negative")
  assert.equal(b.material, false)
})

test("unscored item -> neutral, not material", () => {
  const [a] = toNewsItems([item({ scores: [] })], NOW)
  assert.equal(a.sentiment, "neutral")
  assert.equal(a.material, false)
  assert.equal(a.stress, "none")
})

test("time relative, url and ids pass through", () => {
  const [a] = toNewsItems([item({})], NOW)
  assert.equal(a.time, "3 hours ago")
  assert.equal(a.url, "https://x.test/a")
  assert.equal(a.id, "1")
})

test("crowd odds -> rounded percent", () => {
  assert.deepEqual(toCrowdOdds([{ market_id: "m", question: "Q?", yes_prob: 0.614, liquidity: 1, end_date: null, url: "u", category: "c" }] as never), [{ question: "Q?", probability: 61 }])
})

test("only http(s) urls are kept", () => {
  const u = (v: string) => toNewsItems([item({ url: v })], NOW)[0].url
  assert.equal(u("javascript:alert(1)"), null)
  assert.equal(u("ftp://x"), null)
  assert.equal(u("https://ok"), "https://ok")
})

const hold = (o: Record<string, unknown>) => ({ ticker: "NVDA", name: "NVIDIA", quantity: 86, value: 1000, cost_basis: 900, weight: 0.2191, ...o }) as never
const pt = (date: string, sentiment: number, channel = "news") => ({ date, channel, sentiment, items: 1 })

test("holdings: weight -> percent 1dp, qty/dayChange mapped", () => {
  const [h] = toHoldings([hold({})], {})
  assert.equal(h.weight, 21.9)
  assert.equal(h.qty, 86)
  assert.equal(h.dayChange, 0)
  assert.equal(h.name, "NVIDIA")
})

test("holdings: sentiment is last 7 news values, oldest first; none -> []", () => {
  const pts = Array.from({ length: 9 }, (_, i) => pt(`2026-10-0${i + 1}`, i / 10)).reverse()
  const mixed = [...pts, pt("2026-10-09", 0.99, "crowd")]
  assert.deepEqual(toHoldings([hold({})], { NVDA: mixed })[0].sentiment, [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
  assert.deepEqual(toHoldings([hold({ ticker: "AMD" })], { NVDA: mixed })[0].sentiment, [])
  assert.deepEqual(toHoldings([], {}), [])
})

test("sentiment series: news only, sorted by date, reddit null, regime normal", () => {
  const s = toSentimentSeries([pt("2026-10-02", 0.4), pt("2026-10-01", -0.2), pt("2026-10-01", 0.9, "crowd")])
  assert.deepEqual(s, [
    { day: "10-01", news: -0.2, reddit: null, regime: "normal" },
    { day: "10-02", news: 0.4, reddit: null, regime: "normal" },
  ])
  assert.deepEqual(toSentimentSeries([]), [])
})

test("holdings: null ticker kept (empty ticker, named), null name/qty/value defaulted", () => {
  const out = toHoldings([hold({ ticker: null, name: "Cash" }), hold({ name: null, quantity: null, value: null })], {})
  assert.equal(out.length, 2)
  assert.deepEqual([out[0].ticker, out[0].name], ["", "Cash"])
  assert.deepEqual([out[1].name, out[1].qty, out[1].value], ["NVDA", 0, 0])
})
