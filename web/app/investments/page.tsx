import { AllocationDonut } from "@/components/investment-charts"
import { PageHeading } from "@/components/page-heading"
import { SentimentPanel } from "@/components/sentiment-panel"
import { Sparkline } from "@/components/sparkline"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { components } from "@/lib/api-types"
import { toHoldings, toSentimentSeries } from "@/lib/news-adapters"
import { apiGet } from "@/lib/server-api"

export const dynamic = "force-dynamic"

const MAX_SENTIMENT_TICKERS = 10
const SOON = "Coming with the advisor"

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-sm font-normal text-muted-foreground">{label}</CardTitle></CardHeader>
      <CardContent>
        <p className="numeric text-2xl font-medium tracking-tight">{value}</p>
        {note && <p className="mt-1 text-[11px] text-muted-foreground">{note}</p>}
      </CardContent>
    </Card>
  )
}

export default async function InvestmentsPage() {
  const raw = await apiGet<components["schemas"]["HoldingOut"][]>("/api/holdings")
  const base = raw ? toHoldings(raw, {}) : []
  if (!raw || !base.length) {
    return (
      <div>
        <PageHeading title="Investments" description="Portfolio performance, exposure, and market intelligence." />
        <Card>
          <CardHeader>
            <CardTitle className="serif-display text-3xl">No <em>investments</em> linked</CardTitle>
            <CardDescription>{raw ? "Link a brokerage account to see your holdings." : "The API isn't reachable right now."}</CardDescription>
          </CardHeader>
        </Card>
      </div>
    )
  }
  const tickers = base.slice(0, MAX_SENTIMENT_TICKERS).map((h) => h.ticker)
  const fetched = await Promise.all(
    tickers.map((t) => apiGet<components["schemas"]["SentimentPoint"][]>(`/api/sentiment?ticker=${encodeURIComponent(t)}&days=30`)),
  )
  const sentiment = Object.fromEntries(tickers.map((t, i) => [t, fetched[i] ?? []]))
  const holdings = toHoldings(raw, sentiment)
  const series = Object.fromEntries(tickers.map((t) => [t, toSentimentSeries(sentiment[t])]))
  const total = holdings.reduce((sum, h) => sum + h.value, 0)

  return (
    <div>
      <PageHeading title="Investments" description="Portfolio performance, exposure, and market intelligence." />
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Portfolio value" value={`$${Math.round(total).toLocaleString()}`} />
        <Tile label="Day P&L" value="—" note={SOON} />
        <Tile label="Total return" value="—" note={SOON} />
        <Tile label="Beta vs SPY" value="—" note={SOON} />
      </div>
      <Card className="mb-6">
        <CardHeader><CardTitle>Holdings</CardTitle><CardDescription>Linked brokerage accounts</CardDescription></CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader><TableRow><TableHead>Ticker</TableHead><TableHead>Name</TableHead><TableHead className="text-right">Qty</TableHead><TableHead className="text-right">Value</TableHead><TableHead className="text-right">Weight</TableHead><TableHead className="text-right">Day</TableHead><TableHead>Sentiment</TableHead></TableRow></TableHeader>
            <TableBody>
              {holdings.map((h) => (
                <TableRow key={h.ticker}>
                  <TableCell className="font-mono font-medium text-primary">{h.ticker}</TableCell>
                  <TableCell>{h.name}</TableCell>
                  <TableCell className="numeric text-right">{h.qty}</TableCell>
                  <TableCell className="numeric text-right">${Math.round(h.value).toLocaleString()}</TableCell>
                  <TableCell className="numeric text-right">{h.weight}%</TableCell>
                  <TableCell className="numeric text-right text-muted-foreground">—</TableCell>
                  <TableCell>{h.sentiment.length ? <Sparkline values={h.sentiment} /> : <span className="text-muted-foreground">—</span>}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <div className="mb-6 grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Allocation</CardTitle><CardDescription>Portfolio weight by ticker</CardDescription></CardHeader>
          <CardContent><AllocationDonut data={holdings.map((h) => ({ name: h.ticker, value: h.weight }))} /></CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle>Risk profile</CardTitle><CardDescription>Volatility, drawdown and concentration</CardDescription></CardHeader>
          <CardContent><p className="py-16 text-center text-sm text-muted-foreground">{SOON}</p></CardContent>
        </Card>
      </div>
      <SentimentPanel series={series} />
    </div>
  )
}
