const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000"

/** GET from the API on the server; null when the API is down or errors. */
export async function apiGet<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_URL}${path}`, { cache: "no-store" })
    return res.ok ? ((await res.json()) as T) : null
  } catch {
    return null
  }
}
