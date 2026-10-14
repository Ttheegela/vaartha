import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"
import { canonicalRedirectUrl, lockPath, needsSession, RETURN_PATH_HEADER, returnPath, SESSION_COOKIE } from "./lib/auth.ts"
import { httpsRedirectUrl } from "./lib/https-redirect.ts"

const HTTPS_REDIRECT_STATUS = 308

/** Next 16 "proxy" (formerly middleware): http→https when FORCE_HTTPS=1; with VARTA_AUTH=1, the
 * canonical passkey origin and a lock-page redirect when there is no session cookie (the API validates it). */
export function proxy(request: NextRequest) {
  const pathWithQuery = request.nextUrl.pathname + request.nextUrl.search
  const host = request.headers.get("host")
  const target = httpsRedirectUrl(host, pathWithQuery, request.headers.get("x-forwarded-proto"), process.env.FORCE_HTTPS === "1")
  if (target) return NextResponse.redirect(target, HTTPS_REDIRECT_STATUS)
  // Tell server pages where the request was going, so a 401 can return here after unlock.
  const headers = new Headers(request.headers)
  headers.set(RETURN_PATH_HEADER, returnPath(request.nextUrl))
  const pass = () => NextResponse.next({ request: { headers } })
  if (process.env.VARTA_AUTH !== "1") return pass()
  const effectiveHost = request.headers.get("x-forwarded-host")?.split(",")[0].trim() || host
  const canonical = canonicalRedirectUrl(effectiveHost, pathWithQuery, process.env.PASSKEY_ORIGIN)
  if (canonical) return NextResponse.redirect(canonical, HTTPS_REDIRECT_STATUS)
  if (needsSession(request.nextUrl.pathname) && !request.cookies.has(SESSION_COOKIE)) {
    // Base on the canonical origin: behind `tailscale serve`, nextUrl is http:// on the tailnet host.
    return NextResponse.redirect(new URL(lockPath(returnPath(request.nextUrl)), process.env.PASSKEY_ORIGIN || request.nextUrl))
  }
  return pass()
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] }
