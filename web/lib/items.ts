import type { components } from "./api-types.ts"

type Item = components["schemas"]["ItemOut"]
export const LOGIN_REQUIRED = "login_required"
export const NOT_FOUND = "not_found" // removed or revoked at Plaid; needs a fresh link

/** Per-institution sync info: newest last_synced_at, and whether any of its items needs re-login. */
export function institutionStatus(items: Item[], institution: string): { lastSyncedAt: string | null; needsLogin: boolean } {
  const own = items.filter((i) => (i.institution ?? "Unknown") === institution)
  const lastSyncedAt = own.map((i) => i.last_synced_at).filter((s): s is string => !!s).sort().at(-1) ?? null
  return { lastSyncedAt, needsLogin: own.some((i) => i.status === LOGIN_REQUIRED) }
}

export const REMOVED_BADGE = "Removed at bank — link again"
export type EmptyItem = { id: string; title: string; badge: "Needs re-login" | "Sync failed" | typeof REMOVED_BADGE | null }

/** Items whose institution has no accounts on the page, each with a status badge (null when healthy). */
export function itemsWithoutAccounts(items: Item[], accountInstitutions: string[]): EmptyItem[] {
  return items
    .filter((i) => !accountInstitutions.includes(i.institution ?? "Unknown"))
    .map((i) => ({
      id: i.item_id,
      title: i.institution ?? "Unnamed institution",
      badge: i.status === NOT_FOUND ? REMOVED_BADGE : i.status === LOGIN_REQUIRED ? "Needs re-login" : i.last_synced_at === null ? "Sync failed" : null,
    }))
}

/** The item to reconnect (Link update mode) for an institution, or null when none needs re-login. */
export function reconnectItemId(items: Item[], institution: string): string | null {
  return items.find((i) => (i.institution ?? "Unknown") === institution && i.status === LOGIN_REQUIRED)?.item_id ?? null
}
