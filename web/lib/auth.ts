/** Pure helpers for the owner passkey lock (cookie forwarding, redirects, error text). */

export const SESSION_COOKIE = "varta_session"
export const VISITOR_COOKIE = "varta_vid"
export const LOCK_PATH = "/lock"
export const RETURN_PATH_HEADER = "x-varta-path" // set by proxy.ts (overwriting any client value)

const VISITOR_ID = /^[a-f0-9]{32}$/
const SESSION_TOKEN = /^[A-Za-z0-9_-]{43}$/ // secrets.token_urlsafe(32)
const UNSAFE_NEXT = /[\\\u0000-\u001f\u007f]/
const NEXT_BASE = "http://next.invalid"
const PUBLIC_PATHS = new Set([LOCK_PATH, "/manifest.webmanifest", "/favicon.ico"])
const PUBLIC_PREFIXES = ["/api/", "/_next/"]
const APP_ICON = /^\/(apple-)?icon\d*(\.\w+)?$/ // Next metadata icon routes: /icon.svg, /icon1.png, /apple-icon.png
const RSC_PARAM = "_rsc"

/** Cookie header for the API: the visitor id and session token, each only if well-formed. */
export function apiCookieHeader(visitorId?: string, sessionToken?: string): string | undefined {
  const parts = [
    visitorId && VISITOR_ID.test(visitorId) ? `${VISITOR_COOKIE}=${visitorId}` : null,
    sessionToken && SESSION_TOKEN.test(sessionToken) ? `${SESSION_COOKIE}=${sessionToken}` : null,
  ].filter(Boolean)
  return parts.length ? parts.join("; ") : undefined
}

/** Normalized `raw` if it is a same-site relative path (and not the lock page itself), else "/". */
export function safeNext(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || UNSAFE_NEXT.test(raw)) return "/"
  const url = new URL(raw, NEXT_BASE)
  if (url.origin !== NEXT_BASE || url.pathname.startsWith("//") || url.pathname === LOCK_PATH) return "/"
  return url.pathname + url.search + url.hash
}

/** Path and query to return to after unlocking, without Next's `_rsc` cache-buster. */
export function returnPath(url: URL): string {
  const u = new URL(url.href)
  u.searchParams.delete(RSC_PARAM)
  return u.pathname + u.search
}

/** The lock page URL that returns to `pathWithQuery` after unlocking. */
export function lockPath(pathWithQuery: string): string {
  const next = safeNext(pathWithQuery)
  return next === "/" ? LOCK_PATH : `${LOCK_PATH}?next=${encodeURIComponent(next)}`
}

/** Whether a page path needs a session cookie (false for the lock page, the API and app assets). */
export function needsSession(pathname: string): boolean {
  return !(PUBLIC_PATHS.has(pathname) || PUBLIC_PREFIXES.some((p) => pathname.startsWith(p)) || APP_ICON.test(pathname))
}

/** Same path on the passkey origin when the request came in on another host, else null. */
export function canonicalRedirectUrl(host: string | null, pathWithQuery: string, origin: string | undefined): string | null {
  if (!host || !origin) return null
  const want = new URL(origin)
  return host.toLowerCase() === want.host ? null : `${want.origin}${pathWithQuery}`
}

/** Plain-language message for a failed passkey ceremony or verify call; setup is suggested only when none exists. */
export function ceremonyErrorMessage(err: { name?: string; code?: string; status?: number }, hasCredentials = true): string {
  if (err.status === 403) return "That setup code is invalid or expired. Make a new one on your Mac."
  if (err.status === 409 || err.code === "ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED") return "This device already has a passkey for Vārtā. Unlock instead."
  if (err.status === 401) return hasCredentials ? "Couldn't verify the passkey. Try again." : "No passkey for Vārtā yet. Set one up below."
  if (err.name === "NotAllowedError" || err.name === "AbortError") return "Cancelled, or no passkey for Vārtā on this device."
  return "Something went wrong. Try again."
}
