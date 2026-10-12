export type Segment = { kind: "text"; text: string } | { kind: "cite"; n: number; id: number }

/** Turn `[n:ID]` markers into numbered cites (1-based by source order); unknown ids are dropped. */
export function splitCitations(text: string, sources: { id: number }[]): Segment[] {
  const out: Segment[] = []
  let last = 0
  for (const m of text.matchAll(/\[n:(\d+)\]/g)) {
    const id = Number(m[1]), idx = sources.findIndex((s) => s.id === id)
    const before = text.slice(last, m.index)
    if (before) out.push({ kind: "text", text: before })
    if (idx >= 0) out.push({ kind: "cite", n: idx + 1, id })
    last = m.index + m[0].length
  }
  const tail = text.slice(last)
  if (tail || out.length === 0) out.push({ kind: "text", text: tail })
  return out
}
