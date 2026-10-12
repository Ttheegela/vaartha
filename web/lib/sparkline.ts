const DEFAULT_PAD = 2
const round = (n: number) => Math.round(n * 100) / 100

/** SVG path for a sparkline; y is inverted so higher values sit higher. */
export function sparklinePath(values: number[], width: number, height: number, pad = DEFAULT_PAD): string {
  const pts = values.filter((v) => Number.isFinite(v))
  if (pts.length === 0) return ""
  const series = pts.length === 1 ? [pts[0], pts[0]] : pts
  const min = Math.min(...series)
  const max = Math.max(...series)
  const innerW = width - 2 * pad
  const innerH = height - 2 * pad
  const step = innerW / (series.length - 1)
  const y = (v: number) => (max === min ? height / 2 : pad + ((max - v) / (max - min)) * innerH)
  return series
    .map((v, i) => `${i === 0 ? "M" : "L"}${round(pad + i * step)} ${round(y(v))}`)
    .join(" ")
}
