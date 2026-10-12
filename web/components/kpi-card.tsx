import { ArrowDownRight, ArrowUpRight } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

export function KpiCard({ label, value, delta, up = true }: { label: string; value: string; delta: string; up?: boolean }) {
  return <Card><CardHeader><CardTitle className="text-sm font-normal text-muted-foreground">{label}</CardTitle></CardHeader><CardContent><div className="flex items-end justify-between gap-3"><p className="numeric text-2xl font-medium tracking-tight">{value}</p><span className={up ? "flex items-center font-mono text-xs text-primary" : "flex items-center font-mono text-xs text-destructive"}>{up ? <ArrowUpRight className="size-3.5" /> : <ArrowDownRight className="size-3.5" />}{delta}</span></div><p className="mt-1 text-[11px] text-muted-foreground">vs last month</p></CardContent></Card>
}
