"use client"
import { useMemo, useState } from "react"
import { StatusBadge } from "@/components/status-badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import type { LiveNewsItem } from "@/lib/news-adapters"

export function NewsView({ items, odds }: { items: LiveNewsItem[]; odds: { question: string; probability: number }[] }) {
  const [source, setSource] = useState("all")
  const [ticker, setTicker] = useState("all")
  const [material, setMaterial] = useState(false)
  const sources = useMemo(() => [...new Set(items.map((n) => n.source))].sort(), [items])
  const tickers = useMemo(() => [...new Set(items.flatMap((n) => n.tickers))].sort(), [items])
  const shown = useMemo(
    () => items.filter((n) => (source === "all" || n.source === source) && (ticker === "all" || n.tickers.includes(ticker)) && (!material || n.material)),
    [items, source, ticker, material],
  )
  return (
    <>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Select value={source} onValueChange={(v) => setSource(v ?? "all")}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent><SelectGroup>
            <SelectItem value="all">All sources</SelectItem>
            {sources.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectGroup></SelectContent>
        </Select>
        <Select value={ticker} onValueChange={(v) => setTicker(v ?? "all")}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent><SelectGroup>
            <SelectItem value="all">All tickers</SelectItem>
            {tickers.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
          </SelectGroup></SelectContent>
        </Select>
        <label className="ml-auto flex items-center gap-2 text-sm text-muted-foreground"><Switch checked={material} onCheckedChange={setMaterial} />Only material</label>
      </div>
      <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
        <div className="flex flex-col gap-3">
          {shown.map((item) => (
            <Card key={item.id} size="sm">
              <CardHeader>
                <CardDescription className="numeric">{item.source} · {item.time}</CardDescription>
                <CardTitle className="text-base leading-6">
                  {item.url ? <a href={item.url} target="_blank" rel="noopener noreferrer" className="hover:underline">{item.title}</a> : item.title}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {item.tickers.map((t) => <StatusBadge key={t}>{t}</StatusBadge>)}
                <StatusBadge tone={item.sentiment === "positive" ? "positive" : item.sentiment === "negative" ? "negative" : "neutral"}>{item.sentiment === "positive" ? "+" : item.sentiment === "negative" ? "−" : "0"} sentiment</StatusBadge>
                <StatusBadge tone={item.stress === "systemic" || item.stress === "sector" ? "warning" : "neutral"}>{item.stress}</StatusBadge>
                {item.event && <StatusBadge>{item.event}</StatusBadge>}
              </CardContent>
            </Card>
          ))}
          {!shown.length && <p className="text-sm text-muted-foreground">No headlines match these filters.</p>}
        </div>
        <aside>
          <Card className="sticky top-24">
            <CardHeader><CardTitle>Crowd odds</CardTitle><CardDescription>Polymarket implied probability</CardDescription></CardHeader>
            <CardContent className="flex flex-col gap-5">
              {odds.map((m) => (
                <div key={m.question} className="flex flex-col gap-2">
                  <div className="flex items-start justify-between gap-3"><p className="text-sm leading-5">{m.question}</p><span className="numeric text-primary">{m.probability}%</span></div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-secondary"><div className="h-full bg-primary" style={{ width: `${m.probability}%` }} /></div>
                </div>
              ))}
              {!odds.length && <p className="text-sm text-muted-foreground">No markets available.</p>}
              <p className="text-[11px] leading-5 text-muted-foreground">Prediction markets reflect crowd pricing, not Vārtā forecasts.</p>
            </CardContent>
          </Card>
        </aside>
      </div>
    </>
  )
}
