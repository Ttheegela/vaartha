"use client"
import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { usePlaidLink, type PlaidLinkError, type PlaidLinkOnEventMetadata, type PlaidLinkOnExitMetadata, type PlaidLinkOnSuccessMetadata } from "react-plaid-link"
import { Link2 } from "lucide-react"
import { apiUrl } from "@/lib/api-base"
import { clearLinkSession, linkEventPayload, saveLinkSession } from "@/lib/plaid-link"
import { Button } from "@/components/ui/button"

const PLAID_SCRIPT = "https://cdn.plaid.com/link/v2/stable/link-initialize.js"
let scriptPromise: Promise<void> | null = null

/** Load link-initialize.js exactly once per page. react-plaid-link's own loader removes and re-adds the
 *  tag under React StrictMode, which embeds the script twice and can drop Link's callbacks. */
function loadPlaidScript(): Promise<void> {
  scriptPromise ??= new Promise((resolve, reject) => {
    const el = document.createElement("script")
    el.src = PLAID_SCRIPT
    el.async = true
    el.onload = () => resolve()
    el.onerror = () => {
      scriptPromise = null
      el.remove()
      reject(new Error("Plaid Link failed to load"))
    }
    document.head.appendChild(el)
  })
  return scriptPromise
}

const storage = () => (typeof window === "undefined" ? null : window.localStorage)

/** Fire-and-forget telemetry: allowlisted metadata only, never tokens. */
function postLinkEvent(event: string, metadata: Record<string, unknown>) {
  fetch(apiUrl("/api/plaid/link_event"), {
    method: "POST", credentials: "include", keepalive: true, headers: { "Content-Type": "application/json" },
    body: JSON.stringify(linkEventPayload(event, metadata)),
  }).catch(() => {})
}

type Props = { token: string; itemId: string | null; receivedRedirectUri?: string; label: string; onDone: () => void }

/** One Plaid Link handler. Opens on click, or immediately when resuming an OAuth redirect. */
function PlaidLauncher({ token, itemId, receivedRedirectUri, label, onDone }: Props) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onSuccess = useCallback(async (publicToken: string | null, metadata: PlaidLinkOnSuccessMetadata) => {
    const institutionId = metadata.institution?.institution_id ?? null
    postLinkEvent("ON_SUCCESS", { link_session_id: metadata.link_session_id, institution_id: institutionId })
    clearLinkSession(storage())
    setBusy(true)
    // Update mode returns no new item: the existing access token works again, so just re-sync.
    const r = await (itemId || !publicToken
      ? fetch(apiUrl("/api/sync"), { method: "POST", credentials: "include" })
      : fetch(apiUrl("/api/plaid/exchange"), {
          method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ public_token: publicToken, institution_id: institutionId }),
        })).catch(() => null)
    setBusy(false)
    if (r?.ok) return onDone()
    setError(r?.status === 409 ? "That bank is already linked. Use Reconnect on it if it needs a login." : "Couldn't link that account. Try again.")
  }, [itemId, onDone])

  const onExit = useCallback((err: PlaidLinkError | null, metadata: PlaidLinkOnExitMetadata) => {
    postLinkEvent("ON_EXIT", { ...metadata, institution_id: metadata.institution?.institution_id, error_type: err?.error_type, error_code: err?.error_code })
    clearLinkSession(storage())
    if (err) setError(err.display_message ?? "The bank connection didn't finish. Try again.")
    else if (receivedRedirectUri) onDone()
  }, [receivedRedirectUri, onDone])

  const onEvent = useCallback((name: string, metadata: PlaidLinkOnEventMetadata) => {
    postLinkEvent(name, metadata as unknown as Record<string, unknown>)
  }, [])

  const { open, ready } = usePlaidLink({ token, receivedRedirectUri, onSuccess, onExit, onEvent })
  const resumed = useRef(false)

  useEffect(() => {
    if (!receivedRedirectUri || !ready || resumed.current) return
    resumed.current = true
    open() // OAuth resume must not wait for a click
  }, [receivedRedirectUri, ready, open])

  function start() {
    setError(null)
    saveLinkSession(storage(), { token, itemId })
    open()
  }

  return (
    <div className="flex flex-col items-end gap-1">
      {!receivedRedirectUri && (
        <Button onClick={start} disabled={!ready || busy} className="action-label">
          <Link2 data-icon="inline-start" /> {busy ? "LINKING…" : label}
        </Button>
      )}
      {error && <p className="text-xs text-muted-foreground">{error}</p>}
    </div>
  )
}

/** Resolves once link-initialize.js is on the page (undefined while loading, false if it failed). */
function usePlaidScript(): boolean | undefined {
  const [loaded, setLoaded] = useState<boolean | undefined>(undefined)
  useEffect(() => {
    let live = true
    loadPlaidScript().then(() => live && setLoaded(true), () => live && setLoaded(false))
    return () => { live = false }
  }, [])
  return loaded
}

/** "Link account" (or, with itemId, "Reconnect" in update mode). Pre-initializes Link on page load. */
export function LinkAccountButton({ itemId = null, label = "LINK ACCOUNT" }: { itemId?: string | null; label?: string }) {
  const router = useRouter()
  const scriptLoaded = usePlaidScript()
  const [token, setToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    fetch(apiUrl("/api/plaid/link_token"), {
      method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(itemId ? { item_id: itemId } : {}),
    })
      .then(async (r) => { if (live) r.ok ? setToken((await r.json()).link_token) : setError("Account linking is unavailable") })
      .catch(() => live && setError("Account linking is unavailable"))
    return () => { live = false }
  }, [itemId])

  const onDone = useCallback(() => router.refresh(), [router])
  if (scriptLoaded === false) return <p className="text-xs text-muted-foreground">Plaid couldn&apos;t load. Reload the page.</p>
  if (error) return <p className="text-xs text-muted-foreground">{error}</p>
  if (!token || !scriptLoaded) {
    return <Button disabled className="action-label"><Link2 data-icon="inline-start" /> {label}</Button>
  }
  return <PlaidLauncher token={token} itemId={itemId} label={label} onDone={onDone} />
}

/** Re-opens Link after an OAuth bank redirect with the saved link_token and the full return URL. */
export function OAuthResume({ token, itemId, receivedRedirectUri }: { token: string; itemId: string | null; receivedRedirectUri: string }) {
  const router = useRouter()
  const scriptLoaded = usePlaidScript()
  const onDone = useCallback(() => router.replace("/accounts"), [router])
  if (scriptLoaded === false) return <p className="text-sm text-muted-foreground">Plaid couldn&apos;t load. Reload the page.</p>
  if (!scriptLoaded) return <p className="text-sm text-muted-foreground">Resuming your bank connection…</p>
  return <PlaidLauncher token={token} itemId={itemId} receivedRedirectUri={receivedRedirectUri} label="" onDone={onDone} />
}
