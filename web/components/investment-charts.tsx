"use client"
import { Area, CartesianGrid, Cell, ComposedChart, Line, Pie, PieChart, XAxis, YAxis } from "recharts"
import type { SentimentRow } from "@/lib/news-adapters"
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"

const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"]
const color = (i: number) => PALETTE[i % PALETTE.length]

export function AllocationDonut({ data }: { data: { name: string; value: number }[] }){ const config = Object.fromEntries(data.map((d, i) => [d.name, { label: d.name, color: color(i) }])); return <ChartContainer config={config} className="h-[260px] w-full aspect-auto"><PieChart><ChartTooltip content={<ChartTooltipContent nameKey="name"/>}/><Pie data={data} dataKey="value" nameKey="name" innerRadius={58} outerRadius={88} strokeWidth={0}>{data.map((d, i)=><Cell key={d.name} fill={color(i)}/>)}</Pie><ChartLegend content={<ChartLegendContent nameKey="name"/>}/></PieChart></ChartContainer> }
export function SentimentChart({ data }: { data: SentimentRow[] }){ return <ChartContainer config={{news:{label:"News",color:"var(--chart-1)"}}} className="h-[300px] w-full aspect-auto"><ComposedChart data={data} margin={{top:10,right:10,left:-20,bottom:0}}><CartesianGrid vertical={false}/><XAxis dataKey="day" axisLine={false} tickLine={false}/><YAxis domain={[-1,1]} ticks={[-1,-.5,0,.5,1]} axisLine={false} tickLine={false}/><Area dataKey="news" fill="var(--color-news)" fillOpacity={.05} stroke="none"/><Line type="monotone" dataKey="news" stroke="var(--color-news)" strokeWidth={2} dot={false}/><ChartTooltip content={<ChartTooltipContent/>}/><ChartLegend content={<ChartLegendContent/>}/></ComposedChart></ChartContainer> }
