/** Public https URL for a plain-http request behind a TLS proxy, or null to pass through. */
export function httpsRedirectUrl(
  host: string | null,
  pathWithQuery: string,
  proto: string | null,
  force: boolean,
): string | null {
  if (!force || proto !== "http" || !host) return null
  return `https://${host}${pathWithQuery}`
}
