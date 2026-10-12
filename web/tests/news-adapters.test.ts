import { test } from "node:test"
import assert from "node:assert/strict"
import { toCrowdOdds, toNewsItems } from "../lib/news-adapters.ts"

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
