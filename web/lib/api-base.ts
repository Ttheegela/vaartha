/** Browser-side API URL: prefixes NEXT_PUBLIC_API_BASE (build-time) so the demo web can call a cross-origin API. */
export function apiUrl(path: string, base = process.env.NEXT_PUBLIC_API_BASE ?? ""): string {
  if (!path.startsWith("/")) throw new Error(`apiUrl path must start with "/": ${path}`)
  return base.replace(/\/+$/, "") + path
}
