import type { Budget, DataSource } from "./types"

export const budgets: Budget[] = [
  { category: "Dining", spent: 492, limit: 600 }, { category: "Groceries", spent: 418, limit: 650 },
  { category: "Shopping", spent: 610, limit: 500 }, { category: "Transport", spent: 184, limit: 350 },
  { category: "Entertainment", spent: 238, limit: 300 },
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
