import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"
import { httpsRedirectUrl } from "./lib/https-redirect.ts"

const HTTPS_REDIRECT_STATUS = 308

/** Next 16 "proxy" (formerly middleware): redirect http to https when FORCE_HTTPS=1. */
export function proxy(request: NextRequest) {
  const target = httpsRedirectUrl(
    request.headers.get("host"),
    request.nextUrl.pathname + request.nextUrl.search,
    request.headers.get("x-forwarded-proto"),
    process.env.FORCE_HTTPS === "1",
  )
  return target ? NextResponse.redirect(target, HTTPS_REDIRECT_STATUS) : NextResponse.next()
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] }
