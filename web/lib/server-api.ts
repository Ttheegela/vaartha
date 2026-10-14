import { cookies, headers } from "next/headers"
import { redirect } from "next/navigation"
import { apiCookieHeader, lockPath, RETURN_PATH_HEADER, SESSION_COOKIE, VISITOR_COOKIE } from "./auth.ts"

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000"
const UNAUTHORIZED = 401

/** GET from the API on the server, forwarding the visitor and session cookies.
 * Null when the API is down or errors; a 401 (owner lock) redirects to the lock page. */
export async function apiGet<T>(path: string): Promise<T | null> {
  const jar = await cookies()
  const cookie = apiCookieHeader(jar.get(VISITOR_COOKIE)?.value, jar.get(SESSION_COOKIE)?.value)
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { cache: "no-store", headers: cookie ? { Cookie: cookie } : undefined })
  } catch {
    return null
  }
  // redirect() throws NEXT_REDIRECT, so it stays outside any try; lockPath runs the path through safeNext.
  if (res.status === UNAUTHORIZED) redirect(lockPath((await headers()).get(RETURN_PATH_HEADER) ?? "/"))
  if (!res.ok) return null
  try {
    return (await res.json()) as T
  } catch {
    return null
  }
}
