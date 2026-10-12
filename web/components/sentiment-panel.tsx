"use client"
import { useState } from "react"
import { SentimentChart } from "@/components/investment-charts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import type { SentimentRow } from "@/lib/news-adapters"

export function SentimentPanel({ series }: { series: Record<string, SentimentRow[]> }) {
  const tickers = Object.keys(series)
  const [ticker, setTicker] = useState(tickers[0])
  const data = series[ticker] ?? []
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div><CardTitle>Sentiment</CardTitle><CardDescription>News sentiment · last 30 days</CardDescription></div>
          <Select value={ticker} onValueChange={(v) => setTicker(v ?? tickers[0])}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent><SelectGroup>{tickers.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectGroup></SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {data.length ? <SentimentChart data={data} /> : <p className="py-16 text-center text-sm text-muted-foreground">No scored news for {ticker} yet.</p>}
      </CardContent>
    </Card>
  )
}
