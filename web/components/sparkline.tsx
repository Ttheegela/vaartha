"use client"
import { Line, LineChart } from "recharts"
import { ChartContainer } from "@/components/ui/chart"
export function Sparkline({ values }: { values:number[] }){ const data=values.map((value,i)=>({i,value})); const positive=values.at(-1)!>=0; return <ChartContainer config={{value:{color:positive?"var(--chart-1)":"var(--chart-3)"}}} className="h-8 w-20 aspect-auto"><LineChart data={data}><Line dataKey="value" stroke="var(--color-value)" dot={false} strokeWidth={1.5}/></LineChart></ChartContainer> }
