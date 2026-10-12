import type { Budget, DataSource, Holding } from "./types"

export const budgets: Budget[] = [
  { category: "Dining", spent: 492, limit: 600 }, { category: "Groceries", spent: 418, limit: 650 },
  { category: "Shopping", spent: 610, limit: 500 }, { category: "Transport", spent: 184, limit: 350 },
  { category: "Entertainment", spent: 238, limit: 300 },
]

export const holdings: Holding[] = [
  { ticker: "NVDA", name: "NVIDIA", qty: 86, value: 12346, weight: 21.9, dayChange: -2.14, sentiment: [.7,.6,.4,.2,-.1,-.3,-.5] },
  { ticker: "SPY", name: "SPDR S&P 500", qty: 19, value: 10982, weight: 19.5, dayChange: .42, sentiment: [.2,.3,.4,.3,.5,.4,.5] },
  { ticker: "TSM", name: "Taiwan Semiconductor", qty: 48, value: 9480, weight: 16.8, dayChange: -1.08, sentiment: [.5,.4,.3,.2,.1,-.1,-.2] },
  { ticker: "GLD", name: "SPDR Gold Shares", qty: 26, value: 7020, weight: 12.5, dayChange: .84, sentiment: [.1,.2,.3,.5,.6,.5,.7] },
  { ticker: "AMD", name: "Advanced Micro Devices", qty: 37, value: 6348, weight: 11.3, dayChange: -1.62, sentiment: [.4,.3,.2,0,-.2,-.1,-.3] },
  { ticker: "XOM", name: "Exxon Mobil", qty: 45, value: 5297, weight: 9.4, dayChange: 1.22, sentiment: [0,.1,.2,.4,.5,.6,.5] },
  { ticker: "LIT", name: "Global X Lithium ETF", qty: 91, value: 4829, weight: 8.6, dayChange: .18, sentiment: [-.3,-.2,0,.1,.2,.1,.3] },
]

export const allocation = holdings.map((h, i) => ({ name: h.ticker, value: h.weight, fill: `var(--color-a${i + 1})` }))
export const sentimentSeries = [
  { day: "Mon", news: .62, reddit: .48, regime: "normal" }, { day: "Tue", news: .45, reddit: .55, regime: "normal" },
  { day: "Wed", news: .18, reddit: .31, regime: "normal" }, { day: "Thu", news: -.08, reddit: .12, regime: "elevated" },
  { day: "Fri", news: -.42, reddit: -.15, regime: "elevated" }, { day: "Sat", news: -.31, reddit: -.24, regime: "elevated" },
  { day: "Sun", news: -.55, reddit: -.36, regime: "elevated" },
]

export const dataSources: DataSource[] = [
  { name:"Plaid", status:"Connected", detail:"4 accounts · synced 2h ago" }, { name:"Alpaca", status:"Connected", detail:"Market data live" },
  { name:"Finnhub", status:"Connected", detail:"News and sentiment" }, { name:"Reddit", status:"Pending approval", detail:"Read-only API access" },
]

export const briefings = [
  "3 bills due this week totaling $214.43", "Regime moved NORMAL → ELEVATED: Brent volatility is rising",
  "Dining spend is at 82% of budget with 11 days left", "NVDA news sentiment turned negative on export controls",
]

export const advisorConversations = [
  { id: "c1", title: "Upcoming bills", preview: "You have 3 bills due this week", time: "Today" },
  { id: "c2", title: "Portfolio exposure", preview: "Semiconductors are 41% of holdings", time: "Yesterday" },
  { id: "c3", title: "Emergency fund", preview: "You are on track for February", time: "Oct 8" },
  { id: "c4", title: "Subscription review", preview: "Three possible cancellations found", time: "Oct 4" },
]
