import type { components } from "./api-types"

export type RegimeOut = components["schemas"]["RegimeOut"]

/** Current regime from the API, or null if the API is down or returns an error. */
export async function getRegime(fetchFn: typeof fetch = fetch): Promise<RegimeOut | null> {
  try {
    const res = await fetchFn("/api/regime", { cache: "no-store" })
    return res.ok ? ((await res.json()) as RegimeOut) : null
  } catch {
    return null
  }
}
