import type { Budget, DataSource, Holding, NewsItem } from "./types"

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

export const news: NewsItem[] = [
  { id:"n1", source:"Reuters", time:"18m", title:"U.S. weighs expanded AI chip export controls, sources say", tickers:["NVDA","AMD"], sentiment:"negative", stress:"sector", event:"regulation", material:true },
  { id:"n2", source:"EDGAR", time:"42m", title:"NVIDIA files 8-K following updated China revenue guidance", tickers:["NVDA"], sentiment:"negative", stress:"localized", event:"earnings", material:true },
  { id:"n3", source:"Finnhub", time:"1h", title:"Oil advances as Gulf shipping risks tighten near-term supply", tickers:["XOM"], sentiment:"positive", stress:"sector", event:"geopolitical", material:true },
  { id:"n4", source:"Alpaca", time:"2h", title:"Gold holds gains as investors reassess rate path", tickers:["GLD"], sentiment:"positive", stress:"none", event:"macro", material:false },
  { id:"n5", source:"GDELT", time:"2h", title:"Taiwan chip supply chain faces renewed logistics delays", tickers:["TSM"], sentiment:"negative", stress:"sector", event:"supply chain", material:true },
  { id:"n6", source:"Reddit", time:"3h", title:"Retail discussion shifts defensive ahead of CPI release", tickers:["SPY","GLD"], sentiment:"neutral", stress:"none", event:"macro", material:false },
  { id:"n7", source:"Reuters", time:"4h", title:"AMD launches new accelerator aimed at inference workloads", tickers:["AMD"], sentiment:"positive", stress:"none", event:"earnings", material:true },
  { id:"n8", source:"RSS", time:"5h", title:"Lithium spot prices stabilize after month-long decline", tickers:["LIT"], sentiment:"positive", stress:"localized", event:"supply chain", material:false },
  { id:"n9", source:"Polymarket", time:"6h", title:"Market odds of December rate cut rise to 61%", tickers:["SPY","GLD"], sentiment:"positive", stress:"none", event:"macro", material:true },
  { id:"n10", source:"Finnhub", time:"7h", title:"S&P futures little changed before inflation print", tickers:["SPY"], sentiment:"neutral", stress:"none", event:"macro", material:false },
  { id:"n11", source:"EDGAR", time:"8h", title:"Exxon updates capital spending outlook", tickers:["XOM"], sentiment:"neutral", stress:"none", event:"earnings", material:false },
  { id:"n12", source:"GDELT", time:"9h", title:"European regulators outline advanced chip subsidy package", tickers:["TSM","AMD"], sentiment:"positive", stress:"localized", event:"regulation", material:true },
  { id:"n13", source:"Reddit", time:"10h", title:"Semiconductor sentiment cools across high-volume forums", tickers:["NVDA","AMD"], sentiment:"negative", stress:"localized", event:"macro", material:false },
  { id:"n14", source:"Reuters", time:"11h", title:"Major miner explores lithium asset combination", tickers:["LIT"], sentiment:"positive", stress:"none", event:"m&a", material:true },
  { id:"n15", source:"Alpaca", time:"12h", title:"Treasury yields ease from session highs", tickers:["SPY","GLD"], sentiment:"neutral", stress:"none", event:"macro", material:false },
]

export const dataSources: DataSource[] = [
  { name:"Plaid", status:"Connected", detail:"4 accounts · synced 2h ago" }, { name:"Alpaca", status:"Connected", detail:"Market data live" },
  { name:"Finnhub", status:"Connected", detail:"News and sentiment" }, { name:"Reddit", status:"Pending approval", detail:"Read-only API access" },
]

export const briefings = [
  "3 bills due this week totaling $214.43", "Regime moved NORMAL → ELEVATED: Brent volatility is rising",
  "Dining spend is at 82% of budget with 11 days left", "NVDA news sentiment turned negative on export controls",
]

export const crowdOdds = [
  { question:"Fed cuts rates in December?", probability:61 }, { question:"Brent above $90 by year-end?", probability:34 }, { question:"U.S. recession before July?", probability:22 },
]

export const highestImpact = { eyebrow: "HIGHEST IMPACT", prefix: "Save", figure: "$612/yr", suffix: "by cancelling 3 unused subscriptions", detail: "Vārtā found recurring charges you have not used in over 60 days." }
export const healthScore = { score: 72, status: "Good foundation", actions: ["Build reserves to 4 months", "Reduce shopping by $110/mo", "Rebalance semiconductor exposure"] }
export const advisorAlerts = [
  { id: "a1", text: "Your Amex statement closes in 4 days.", action: "Pay now", time: "1m ago", kind: "bill" },
  { id: "a2", text: "Spotify went up $2.00/mo.", action: "Review", time: "2h ago", kind: "price" },
  { id: "a3", text: "NVDA sentiment turned negative on export-control news.", action: "See why", time: "3h ago", kind: "market" },
  { id: "a4", text: "Regime moved to ELEVATED — your semis exposure is 41%.", action: "See impact", time: "today", kind: "risk" },
] as const
export const advisorConversations = [
  { id: "c1", title: "Upcoming bills", preview: "You have 3 bills due this week", time: "Today" },
  { id: "c2", title: "Portfolio exposure", preview: "Semiconductors are 41% of holdings", time: "Yesterday" },
  { id: "c3", title: "Emergency fund", preview: "You are on track for February", time: "Oct 8" },
  { id: "c4", title: "Subscription review", preview: "Three possible cancellations found", time: "Oct 4" },
]
