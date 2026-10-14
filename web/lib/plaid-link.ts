/** Pure helpers for the Plaid Link flow: the link_token kept across an OAuth redirect, and telemetry payloads. */

export const LINK_SESSION_KEY = "varta.plaid.link"

/** The Link session to resume after an OAuth bank redirect; itemId is set in update (reconnect) mode. */
export type LinkSession = { token: string; itemId: string | null }

type KV = Pick<Storage, "getItem" | "setItem" | "removeItem">

/** Persist the session before Link opens, so /oauth-return can re-initialize with the same token. */
export function saveLinkSession(storage: KV | null, session: LinkSession): void {
  try {
    storage?.setItem(LINK_SESSION_KEY, JSON.stringify(session))
  } catch {
    // storage blocked: OAuth banks can't resume, non-OAuth banks still work
  }
}

/** The saved session, or null when absent, malformed or storage is unavailable. */
export function loadLinkSession(storage: KV | null): LinkSession | null {
  try {
    const v = JSON.parse(storage?.getItem(LINK_SESSION_KEY) ?? "null")
    return typeof v?.token === "string" ? { token: v.token, itemId: typeof v.itemId === "string" ? v.itemId : null } : null
  } catch {
    return null
  }
}

/** Forget the session once Link finishes (success or exit). */
export function clearLinkSession(storage: KV | null): void {
  try {
    storage?.removeItem(LINK_SESSION_KEY)
  } catch {
    // nothing to clear
  }
}

const TELEMETRY_FIELDS = ["link_session_id", "institution_id", "error_type", "error_code", "view_name", "request_id"] as const
export type LinkEventPayload = { event: string } & Record<(typeof TELEMETRY_FIELDS)[number], string | null>

/** Body for POST /api/plaid/link_event: an allowlist of metadata fields, so tokens never leave the browser. */
export function linkEventPayload(event: string, metadata: Record<string, unknown>): LinkEventPayload {
  const out = { event } as LinkEventPayload
  for (const f of TELEMETRY_FIELDS) {
    const v = metadata[f]
    out[f] = typeof v === "string" ? v : null
  }
  return out
}
