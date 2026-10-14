/** Where to send a plain-http request behind a TLS-terminating proxy, or null to pass through. */
export function httpsRedirectUrl(url: string, proto: string | null, force: boolean): string | null {
  if (!force || proto !== "http") return null
  const u = new URL(url)
  u.protocol = "https:"
  return u.toString()
}
