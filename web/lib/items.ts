import type { components } from "./api-types.ts"

type Item = components["schemas"]["ItemOut"]
export const LOGIN_REQUIRED = "login_required"

/** Per-institution sync info: newest last_synced_at, and whether any of its items needs re-login. */
export function institutionStatus(items: Item[], institution: string): { lastSyncedAt: string | null; needsLogin: boolean } {
  const own = items.filter((i) => (i.institution ?? "Unknown") === institution)
  const lastSyncedAt = own.map((i) => i.last_synced_at).filter((s): s is string => !!s).sort().at(-1) ?? null
  return { lastSyncedAt, needsLogin: own.some((i) => i.status === LOGIN_REQUIRED) }
}
