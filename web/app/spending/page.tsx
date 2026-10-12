import { ArrowRight } from "lucide-react"
import { toBudgets, toMerchantSpend } from "@/lib/adapters"
import type { components } from "@/lib/api-types"
import { usd } from "@/lib/utils"
import { apiGet } from "@/lib/server-api"
import { PageHeading } from "@/components/page-heading"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

export const dynamic = "force-dynamic"

const MONTH_FMT = new Intl.DateTimeFormat("en-US", { month: "long", timeZone: "UTC" })

export default async function SpendingPage() {
  const [spending, budgetData] = await Promise.all([
    apiGet<components["schemas"]["SpendingOut"]>("/api/spending"),
    apiGet<components["schemas"]["BudgetOut"][]>("/api/budgets"),
  ])
  if (!spending) return <div><PageHeading title="Track your spending" description="A clear view of what is available, what is committed, and what can change."/><Card><CardHeader><CardTitle>The API isn't reachable right now.</CardTitle></CardHeader></Card></div>
  if (spending.by_category.length === 0 && spending.cash_flow.every((c) => c.income === 0 && c.spend === 0)) return <div><PageHeading title="Track your spending" description="A clear view of what is available, what is committed, and what can change."/><Card><CardHeader><CardTitle className="serif-display text-3xl">No <em>spending</em> yet</CardTitle><CardDescription>Link an account and Vārtā will chart where your money goes.</CardDescription></CardHeader></Card></div>
  const budgets = budgetData ? toBudgets(budgetData) : []
  const merchantSpend = toMerchantSpend(spending)
  const monthName = MONTH_FMT.format(new Date(`${spending.month}-01T00:00:00Z`))
  const current = spending.cash_flow.find((c) => c.month === spending.month) ?? { income: 0, spend: 0 }
  const cashMax = Math.max(current.income, current.spend, 1)
  const budgetTotal = budgets.reduce((s, b) => s + b.limit, 0)
  const spentTotal = budgets.reduce((s, b) => s + b.spent, 0)
  const left = Math.max(budgetTotal - spentTotal, 0)
  const spentDeg = budgetTotal ? Math.min(spentTotal / budgetTotal, 1) * 360 : 0
  return <div><PageHeading title="Track your spending" description="A clear view of what is available, what is committed, and what can change." action={<Button variant="outline">{monthName.toUpperCase()} {spending.month.slice(0, 4)} <ArrowRight data-icon="inline-end"/></Button>}/><div className="grid gap-6 xl:grid-cols-[1fr_1.25fr]"><Card><CardHeader><p className="eyebrow">MONTHLY BUDGET</p></CardHeader><CardContent><div className="relative mx-auto flex size-64 items-center justify-center rounded-full" style={{background:`conic-gradient(#4f8cff ${spentDeg}deg,#242424 0)`}}><div className="flex size-56 flex-col items-center justify-center rounded-full bg-card text-center"><span className="text-sm text-muted-foreground">Left to spend</span><strong className="serif-display mt-1 text-4xl"><em>{usd(left)}</em></strong><span className="numeric mt-2 text-xs text-muted-foreground">of {usd(budgetTotal)} budget</span></div></div><div className="mt-8 flex flex-col gap-1">{[["Net monthly income",usd(current.income)],["Save",usd(current.income - current.spend)],["Set monthly budget",usd(budgetTotal)]].map(([label,value])=><div key={label} className="flex items-center justify-between border-b py-4 last:border-0"><span className="text-sm text-muted-foreground">{label}</span><span className="numeric text-sm">{value}</span></div>)}</div></CardContent></Card><Card><CardHeader><p className="eyebrow">CATEGORIES</p><CardTitle className="mt-2">Where your money is going</CardTitle></CardHeader><CardContent className="flex flex-col gap-6">{budgets.map((budget) => { const pct=budget.limit?Math.round(budget.spent/budget.limit*100):0; return <div key={budget.category}><div className="mb-2 flex items-end justify-between"><div><p className="text-sm">{budget.category}</p><p className="numeric mt-1 text-xs text-muted-foreground">${budget.spent.toFixed(0)} of ${budget.limit.toFixed(0)}</p></div><span className="numeric text-xs text-muted-foreground">{pct}%</span></div><div className="h-1 overflow-hidden rounded-full bg-secondary"><div className={`h-full rounded-full ${pct>100?"bg-destructive":pct>80?"bg-warning":"bg-[#4f8cff]"}`} style={{width:`${Math.min(pct,100)}%`}}/></div></div>})}</CardContent></Card></div><div className="mt-6 grid gap-6 xl:grid-cols-[1.25fr_1fr]"><Card><CardHeader><p className="eyebrow">CASH FLOW</p><CardTitle>{monthName} overview</CardTitle></CardHeader><CardContent>{[["Income",current.income,cashMax],["Expenses",current.spend,cashMax],["Net cash flow",Math.max(current.income - current.spend, 0),cashMax]].map(([label,value,max])=><div key={label as string} className="border-b py-5 last:border-0"><div className="mb-3 flex justify-between"><span className="text-sm">{label}</span><span className="numeric text-sm">${Number(value).toLocaleString()}</span></div><div className="h-1 rounded-full bg-secondary"><div className={`h-full rounded-full ${label==="Expenses"?"bg-muted-foreground":"bg-[#4f8cff]"}`} style={{width:`${Number(value)/Number(max)*100}%`}}/></div></div>)}</CardContent></Card><Card><CardHeader><p className="eyebrow">SPENDING TRANSACTIONS</p><CardTitle>Top merchants</CardTitle></CardHeader><CardContent className="flex flex-col">{merchantSpend.map((merchant)=><div key={merchant.merchant} className="flex items-center gap-3 border-b py-4 last:border-0"><div className="flex size-9 items-center justify-center rounded-full bg-secondary font-mono text-xs">{merchant.merchant[0]}</div><div className="flex-1"><p className="text-sm">{merchant.merchant}</p><p className="text-xs text-muted-foreground">{merchant.category} · {merchant.transactions} transactions</p></div><span className="numeric text-sm">${merchant.amount.toFixed(2)}</span></div>)}</CardContent></Card></div></div>
}
