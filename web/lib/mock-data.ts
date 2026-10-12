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
