export type BadgeTone = "normal" | "elevated" | "crisis" | "unavailable" | "loading"

const TONES: Record<string, BadgeTone> = { Normal: "normal", Elevated: "elevated", Crisis: "crisis" }

/** Sidebar badge for a regime response: undefined = loading, null = request failed. */
export function regimeBadge(r: { label: string } | null | undefined): { text: string; tone: BadgeTone } {
  if (r === undefined) return { text: "REGIME …", tone: "loading" }
  const tone = r ? TONES[r.label] : undefined
  if (!tone) return { text: "REGIME UNAVAILABLE", tone: "unavailable" }
  return { text: `${r!.label.toUpperCase()} REGIME`, tone }
}
