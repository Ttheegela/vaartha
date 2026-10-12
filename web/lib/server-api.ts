const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000"

const VISITOR_ID = /^[a-f0-9]{32}$/

/** Cookie header for the visitor-id cookie, or undefined unless the value is a valid 32-hex id. */
export function visitorCookieHeader(value?: string): string | undefined {
  return value && VISITOR_ID.test(value) ? `varta_vid=${value}` : undefined
}

/** GET from the API on the server; null when the API is down or errors. */
export async function apiGet<T>(path: string, init?: { cookie?: string }): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store", headers: init?.cookie ? { Cookie: init.cookie } : undefined })
    return res.ok ? ((await res.json()) as T) : null
  } catch {
    return null
  }
}
