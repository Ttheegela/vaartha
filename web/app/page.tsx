import { toBills, toNetWorth } from "@/lib/adapters"
import { usd } from "@/lib/utils"
import { upcomingBills } from "@/lib/calendar"
import type { components } from "@/lib/api-types"
import { apiGet } from "@/lib/server-api"
import { avatarColor, avatarInitial } from "@/lib/avatar"
import { AlertFeed } from "@/components/alert-feed"
import Link from "next/link"
import { NetWorthChart } from "@/components/net-worth-chart"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export const dynamic = "force-dynamic"

const TODAY_FMT = new Intl.DateTimeFormat("en-US", { weekday: "long", month: "long", day: "numeric", timeZone: "UTC" })

export default async function HomePage() {
  const [recurring, points, accounts, briefing, alerts] = await Promise.all([
    apiGet<components["schemas"]["RecurringListOut"]>("/api/recurring"),
    apiGet<components["schemas"]["NetWorthPoint"][]>("/api/networth?days=365"),
    apiGet<components["schemas"]["AccountsOut"]>("/api/accounts"),
    apiGet<components["schemas"]["BriefingOut"]>("/api/briefing"),
    apiGet<components["schemas"]["AlertOut"][]>("/api/alerts"),
  ])
  const now = new Date()
  const upcoming = recurring ? upcomingBills(toBills(recurring, now), now) : []
  const hasAccounts = (accounts?.accounts.length ?? 0) > 0
  const netWorth = accounts ? accounts.assets - accounts.liabilities : 0
  const series = points ? toNetWorth(points) : []
  return <div className="flex flex-col gap-10">
  <section className="relative overflow-hidden rounded-[28px] border bg-card p-6 sm:p-8"><div className="home-grid pointer-events-none absolute inset-0"/><div className="relative max-w-3xl"><p className="eyebrow mb-5">{TODAY_FMT.format(now).toUpperCase()}</p><h1 className="serif-display text-balance text-4xl sm:text-5xl">Good morning, <em>Tarun</em></h1><p className="mt-3 max-w-xl text-base leading-7 text-muted-foreground">Here is where your money stands today.</p></div></section>
  <Card><CardHeader><p className="eyebrow">{briefing ? "TODAY'S HIGHEST IMPACT" : "YOUR ADVISOR"}</p><CardTitle className="serif-display mt-3 text-4xl">{briefing ? briefing.headline : <>No briefing <em>yet</em></>}</CardTitle></CardHeader><CardContent className="flex flex-col gap-4">{briefing ? <>{briefing.bullets.length > 0 && <ul className="flex max-w-2xl list-disc flex-col gap-2 pl-5 text-sm leading-6 text-muted-foreground">{briefing.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>}{briefing.sources.length > 0 && <div className="flex flex-wrap gap-2">{briefing.sources.map((s, i) => <Link key={s.id ?? i} href="/news" className="w-fit rounded-full bg-secondary px-3 py-1 text-[11px] text-muted-foreground hover:text-foreground">[{i + 1}] {s.source} · {s.title}</Link>)}</div>}</> : <p className="max-w-2xl text-sm leading-6 text-muted-foreground">{accounts ? "Briefings are generated each morning." : "The API isn't reachable right now."}</p>}<Link href="/advisor" className="eyebrow w-fit hover:text-foreground">ASK Vārtā →</Link></CardContent></Card>
  {alerts && alerts.length > 0 && <AlertFeed initial={alerts}/>}
  <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]"><Card><CardHeader><p className="eyebrow">NET WORTH</p><CardTitle className="mt-3 text-4xl numeric">{usd(netWorth)}</CardTitle>{!hasAccounts && <p className="mt-2 text-sm text-muted-foreground">{accounts ? "Link an account to see your net worth." : "The API isn't reachable right now."}</p>}</CardHeader><CardContent>{series.length > 0 && <NetWorthChart data={series}/>}</CardContent></Card><Card><CardHeader><p className="eyebrow">UPCOMING</p><CardTitle>Your next seven days</CardTitle></CardHeader><CardContent className="flex flex-col gap-1">{upcoming.length === 0 && <p className="text-sm text-muted-foreground">{recurring ? "Nothing due in the next seven days." : "The API isn't reachable right now."}</p>}{upcoming.map((bill) => <div key={bill.id} className="flex items-center gap-3 border-b py-3 last:border-0"><div style={{backgroundColor:avatarColor(bill.merchant)}} className="flex size-9 items-center justify-center rounded-full text-sm font-semibold text-white">{avatarInitial(bill.merchant)}</div><div className="min-w-0 flex-1"><p className="text-sm">{bill.merchant}</p><p className="numeric text-[10px] text-muted-foreground">{bill.date}</p></div><p className="numeric text-sm">${bill.amount.toFixed(2)}</p></div>)}</CardContent></Card></div>
</div>
}
