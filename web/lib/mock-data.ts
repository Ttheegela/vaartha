import type { Account, Bill, Budget, DataSource, Goal, Holding, MerchantSpend, NewsItem } from "./types"

export const accounts: Account[] = [
  { id: "ch-1", institution: "Chase", name: "Total Checking", type: "Checking", mask: "••4821", balance: 8420.36 },
  { id: "ch-2", institution: "Chase", name: "High Yield Savings", type: "Savings", mask: "••9014", balance: 21680.12 },
  { id: "am-1", institution: "Amex", name: "Blue Cash Preferred", type: "Credit card", mask: "••1008", balance: 2384.72, liability: true },
  { id: "fi-1", institution: "Fidelity", name: "Individual Brokerage", type: "Brokerage", mask: "••7762", balance: 56301.89 },
]

export const netWorth = [
  { month: "Nov", value: 68400 }, { month: "Dec", value: 70100 }, { month: "Jan", value: 72200 }, { month: "Feb", value: 71500 },
  { month: "Mar", value: 74800 }, { month: "Apr", value: 77100 }, { month: "May", value: 75600 }, { month: "Jun", value: 78900 },
  { month: "Jul", value: 80300 }, { month: "Aug", value: 82100 }, { month: "Sep", value: 81600 }, { month: "Oct", value: 84017 },
]

export const kpis = [
  { label: "Net worth", value: "$84,017", delta: "+2.9%", up: true },
  { label: "This month income", value: "$8,240", delta: "+4.1%", up: true },
  { label: "This month spend", value: "$5,126", delta: "+8.4%", up: false },
  { label: "Cash available", value: "$30,100", delta: "+1.7%", up: true },
]

export const bills: Bill[] = [
  { id: "b1", merchant: "Rent", amount: 2450, day: 1, date: "Nov 1", frequency: "Monthly", paid: true },
  { id: "b2", merchant: "Spotify", amount: 11.99, day: 3, date: "Nov 3", frequency: "Monthly", paid: true },
  { id: "b3", merchant: "iCloud", amount: 2.99, day: 5, date: "Nov 5", frequency: "Monthly", paid: true },
  { id: "b4", merchant: "Gym", amount: 64, day: 7, date: "Nov 7", frequency: "Monthly", paid: true },
  { id: "b5", merchant: "ChatGPT", amount: 20, day: 12, date: "Nov 12", frequency: "Monthly", priceUp: 2 },
  { id: "b6", merchant: "Con Edison", amount: 96.43, day: 14, date: "Nov 14", frequency: "Monthly" },
  { id: "b7", merchant: "Netflix", amount: 22.99, day: 15, date: "Nov 15", frequency: "Monthly", priceUp: 2 },
  { id: "b8", merchant: "Verizon", amount: 88, day: 18, date: "Nov 18", frequency: "Monthly" },
  { id: "b9", merchant: "Car insurance", amount: 142.50, day: 21, date: "Nov 21", frequency: "Monthly" },
  { id: "b10", merchant: "Amazon Prime", amount: 139, day: 24, date: "Nov 24", frequency: "Annual" },
  { id: "b11", merchant: "The Atlantic", amount: 7.99, day: 26, date: "Nov 26", frequency: "Monthly", inactive: true },
  { id: "b12", merchant: "Dropbox", amount: 19.99, day: 29, date: "Nov 29", frequency: "Monthly" },
]

export const budgets: Budget[] = [
  { category: "Dining", spent: 492, limit: 600 }, { category: "Groceries", spent: 418, limit: 650 },
  { category: "Shopping", spent: 610, limit: 500 }, { category: "Transport", spent: 184, limit: 350 },
  { category: "Entertainment", spent: 238, limit: 300 },
]

export const categorySpend = [
  { name: "Housing", value: 2450, fill: "var(--color-housing)" }, { name: "Dining", value: 492, fill: "var(--color-dining)" },
  { name: "Groceries", value: 418, fill: "var(--color-groceries)" }, { name: "Shopping", value: 610, fill: "var(--color-shopping)" },
  { name: "Other", value: 1156, fill: "var(--color-other)" },
]

export const merchantSpend: MerchantSpend[] = [
  { merchant: "Whole Foods", category: "Groceries", amount: 286.42, transactions: 6 },
  { merchant: "Sweetgreen", category: "Dining", amount: 174.65, transactions: 8 },
  { merchant: "Amazon", category: "Shopping", amount: 423.18, transactions: 5 },
  { merchant: "Uber", category: "Transport", amount: 132.80, transactions: 9 },
  { merchant: "Trader Joe’s", category: "Groceries", amount: 131.58, transactions: 4 },
]

export const cashFlow = [
  { month: "May", income: 7900, spend: 4880 }, { month: "Jun", income: 8050, spend: 5210 }, { month: "Jul", income: 8050, spend: 4950 },
  { month: "Aug", income: 8120, spend: 5640 }, { month: "Sep", income: 7920, spend: 4720 }, { month: "Oct", income: 8240, spend: 5126 },
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

export const goals: Goal[] = [
  { name:"Emergency fund", current:21680, target:30000, targetDate:"Mar 2027", projectedDate:"Feb 18, 2027", status:"On track" },
  { name:"Japan trip", current:4200, target:8500, targetDate:"Sep 2027", projectedDate:"Aug 4, 2027", status:"On track" },
  { name:"Roth IRA max", current:4100, target:7000, targetDate:"Apr 2027", projectedDate:"May 21, 2027", status:"Behind" },
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
