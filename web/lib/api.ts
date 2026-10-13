import { apiUrl } from "./api-base"
import type { components } from "./api-types"

export type RegimeOut = components["schemas"]["RegimeOut"]

/** Current regime from the API, or null if the API is down or returns an error. */
export async function getRegime(fetchFn: typeof fetch = fetch): Promise<RegimeOut | null> {
  try {
    const res = await fetchFn(apiUrl("/api/regime"), { cache: "no-store", credentials: "include" })
    return res.ok ? ((await res.json()) as RegimeOut) : null
  } catch {
    return null
  }
}
