export type Sentiment = "positive" | "neutral" | "negative"
export type Regime = "NORMAL" | "ELEVATED" | "CRISIS"

export interface Account { id: string; institution: string; name: string; type: string; mask: string; balance: number; liability?: boolean }
export type RecurringKind = "subscription" | "bill"
export interface Bill { id: string; merchant: string; amount: number; day: number; date: string; nextDate: string; frequency: "Monthly" | "Annual" | "Weekly"; paid?: boolean; inactive?: boolean; priceUp?: number; kind: RecurringKind }
export interface Holding { ticker: string; name: string; qty: number; value: number; weight: number; dayChange: number; sentiment: number[] }
export interface NewsItem { id: string; source: string; time: string; title: string; tickers: string[]; sentiment: Sentiment; stress: "none" | "localized" | "sector" | "systemic"; event: string; material: boolean }
export interface Budget { category: string; spent: number; limit: number }
export interface Goal { name: string; current: number; target: number; targetDate: string; projectedDate: string; status: "On track" | "Behind" }
export interface MerchantSpend { merchant: string; category: string; amount: number; transactions: number }
export interface DataSource { name: string; status: "Connected" | "Online" | "Pending approval"; detail: string }
export interface AdvisorAlert { id: string; text: string; action: string; time: string; kind: "bill" | "price" | "market" | "risk" }
export interface AdvisorConversation { id: string; title: string; preview: string; time: string }
export interface HighestImpact { eyebrow: string; prefix: string; figure: string; suffix: string; detail: string }
export interface HealthScore { score: number; status: string; actions: string[] }
