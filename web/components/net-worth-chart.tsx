"use client"
import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart"
import { netWorth } from "@/lib/mock-data"

export function NetWorthChart() { return <ChartContainer config={{ value: { label: "Net worth", color: "var(--chart-1)" } }} className="h-[270px] w-full aspect-auto"><AreaChart data={netWorth} margin={{ left: 0, right: 8, top: 12 }}><defs><linearGradient id="worthFill" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="var(--color-value)" stopOpacity={.28}/><stop offset="95%" stopColor="var(--color-value)" stopOpacity={0}/></linearGradient></defs><CartesianGrid vertical={false} strokeDasharray="3 3" /><XAxis dataKey="month" axisLine={false} tickLine={false} /><YAxis hide domain={[65000, 86000]} /><ChartTooltip content={<ChartTooltipContent formatter={(value) => <span className="numeric">${Number(value).toLocaleString()}</span>} />} /><Area type="monotone" dataKey="value" stroke="var(--color-value)" strokeWidth={2} fill="url(#worthFill)" /></AreaChart></ChartContainer> }
