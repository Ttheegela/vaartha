/** Muted, mutually distinct fills that keep white text readable on #0a0a0a. */
export const AVATAR_COLORS = [
  "#3b5b8c", "#7a4b8c", "#3f7a5a", "#9a5b3a",
  "#8c3b4f", "#2f7a80", "#7a6a2f", "#5a5a6e",
] as const

const FALLBACK_INITIAL = "?"

/** First visible letter of a merchant name, uppercased. */
export function avatarInitial(merchant: string): string {
  const first = [...merchant.trim()][0]
  return first ? first.toLocaleUpperCase() : FALLBACK_INITIAL
}

/** Stable palette color for a merchant (FNV-1a hash of the normalized name). */
export function avatarColor(merchant: string): string {
  let hash = 0x811c9dc5
  for (const ch of merchant.trim().toLowerCase()) {
    hash ^= ch.codePointAt(0) ?? 0
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length]
}
