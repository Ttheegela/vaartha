import { sparklinePath } from "@/lib/sparkline"

const WIDTH = 80
const HEIGHT = 32

export function Sparkline({ values }: { values: number[] }) {
  const d = sparklinePath(values, WIDTH, HEIGHT)
  const last = values.at(-1) ?? 0
  return (
    <svg width={WIDTH} height={HEIGHT} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img"
      aria-label={`Sentiment trend, latest ${last.toFixed(2)}`}>
      <path d={d} fill="none" stroke={last >= 0 ? "var(--chart-1)" : "var(--chart-3)"}
        strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}
