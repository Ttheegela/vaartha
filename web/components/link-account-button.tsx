"use client"
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { usePlaidLink, type PlaidLinkError, type PlaidLinkOnEventMetadata, type PlaidLinkOnExitMetadata, type PlaidLinkOnSuccessMetadata } from "react-plaid-link"
import { Link2, RotateCw } from "lucide-react"
import { apiUrl } from "@/lib/api-base"
import { clearLinkSession, linkEventPayload, saveLinkSession, type LinkSession } from "@/lib/plaid-link"
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

/** True once link-initialize.js is on the page, false if it failed, undefined while loading. */
function usePlaidScript(): boolean | undefined {
  const [loaded, setLoaded] = useState<boolean | undefined>(undefined)
  useEffect(() => {
    let live = true
    loadPlaidScript().then(() => live && setLoaded(true), () => live && setLoaded(false))
    return () => { live = false }
  }, [])
  return loaded
}

const storage = () => {
  try { return typeof window === "undefined" ? null : window.localStorage } catch { return null }
}

/** Fire-and-forget telemetry: allowlisted metadata only, never tokens. */
function postLinkEvent(event: string, metadata: Record<string, unknown>) {
  fetch(apiUrl("/api/plaid/link_event"), {
    method: "POST", credentials: "include", keepalive: true, headers: { "Content-Type": "application/json" },
    body: JSON.stringify(linkEventPayload(event, metadata)),
  }).catch(() => {})
}

async function fetchLinkToken(itemId: string | null): Promise<string | null> {
  const r = await fetch(apiUrl("/api/plaid/link_token"), {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(itemId ? { item_id: itemId } : {}),
  }).catch(() => null)
  return r?.ok ? (await r.json()).link_token : null
}

type Outcome = { ok: boolean; message?: string }
type HandleProps = LinkSession & { autoOpen: boolean; receivedRedirectUri?: string; onReady: (open: (() => void) | null) => void; onBusy: () => void; onFinish: (o: Outcome) => void }

/** The page's single Plaid handler for one link_token. Remount (key = token) to switch tokens: the
 *  previous handler is destroyed before the next is created. Renders nothing. */
function PlaidHandle({ token, itemId, autoOpen, receivedRedirectUri, onReady, onBusy, onFinish }: HandleProps) {
  const onSuccess = useCallback(async (publicToken: string | null, metadata: PlaidLinkOnSuccessMetadata) => {
    const institutionId = metadata.institution?.institution_id ?? null
    postLinkEvent("ON_SUCCESS", { link_session_id: metadata.link_session_id, institution_id: institutionId })
    clearLinkSession(storage())
    onBusy()
    // Update mode returns no new item: the existing access token works again, so just re-sync.
    const r = await (itemId || !publicToken
      ? fetch(apiUrl("/api/sync"), { method: "POST", credentials: "include" })
      : fetch(apiUrl("/api/plaid/exchange"), {
          method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ public_token: publicToken, institution_id: institutionId }),
        })).catch(() => null)
    onFinish(r?.ok ? { ok: true } : {
      ok: false,
      message: r?.status === 409 ? "That bank is already linked. Use Reconnect on it if it needs a login." : "Couldn't link that account. Try again.",
    })
  }, [itemId, onBusy, onFinish])

  const onExit = useCallback((err: PlaidLinkError | null, metadata: PlaidLinkOnExitMetadata) => {
    postLinkEvent("ON_EXIT", { ...metadata, institution_id: metadata.institution?.institution_id, error_type: err?.error_type, error_code: err?.error_code })
    clearLinkSession(storage())
    onFinish(err ? { ok: false, message: err.display_message ?? "The bank connection didn't finish. Try again." } : { ok: false })
  }, [onFinish])

  const onEvent = useCallback((name: string, metadata: PlaidLinkOnEventMetadata) => {
    postLinkEvent(name, metadata as unknown as Record<string, unknown>)
  }, [])

  const { open, ready } = usePlaidLink({ token, receivedRedirectUri, onSuccess, onExit, onEvent })
  const opened = useRef(false)
  const start = useCallback(() => {
    saveLinkSession(storage(), { token, itemId }) // survives an OAuth bank redirect
    open()
  }, [token, itemId, open])

  useEffect(() => {
    onReady(ready ? start : null)
    if (!ready || !autoOpen || opened.current) return
    opened.current = true
    if (receivedRedirectUri) open() // OAuth resume: same session, must not wait for a click
    else start()
  }, [ready, autoOpen, receivedRedirectUri, open, start, onReady])
  return null
}

type LinkApi = { ready: boolean; busy: boolean; error: string | null; link: () => void; reconnect: (itemId: string) => void }
const LinkCtx = createContext<LinkApi | null>(null)

/** One Plaid handler per page. Pre-initializes Link for new banks on page load (open on click);
 *  Reconnect fetches its update-mode token on click and temporarily takes over the handler. */
export function PlaidLinkProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const scriptLoaded = usePlaidScript()
  const [base, setBase] = useState<string | null>(null)
  const [baseNonce, setBaseNonce] = useState(0)
  const [update, setUpdate] = useState<LinkSession | null>(null)
  const [open, setOpen] = useState<(() => void) | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    fetchLinkToken(null).then((t) => { if (live) t ? setBase(t) : setError("Account linking is unavailable") })
    return () => { live = false }
  }, [baseNonce])

  const onReady = useCallback((fn: (() => void) | null) => setOpen(() => fn), [])
  const onBusy = useCallback(() => setBusy(true), [])
  const onFinish = useCallback((o: Outcome) => {
    setBusy(false)
    setError(o.message ?? null)
    setUpdate(null)
    if (o.ok) {
      setBase(null)
      setBaseNonce((n) => n + 1) // a used token is not reused for the next link
      router.refresh()
    }
  }, [router])

  const reconnect = useCallback(async (itemId: string) => {
    setError(null)
    setBusy(true)
    const t = await fetchLinkToken(itemId)
    if (t) setUpdate({ token: t, itemId })
    else { setBusy(false); setError("Reconnect is unavailable right now") }
  }, [])

  const session = update ?? (base ? { token: base, itemId: null } : null)
  const api: LinkApi = {
    ready: !!open && !update && !busy, busy, error: scriptLoaded === false ? "Plaid couldn't load. Reload the page." : error,
    link: () => { setError(null); open?.() }, reconnect,
  }
  return (
    <LinkCtx.Provider value={api}>
      {scriptLoaded && session && (
        <PlaidHandle key={session.token} token={session.token} itemId={session.itemId} autoOpen={!!update} onReady={onReady} onBusy={onBusy} onFinish={onFinish} />
      )}
      {children}
    </LinkCtx.Provider>
  )
}

function useLinkApi(): LinkApi {
  const api = useContext(LinkCtx)
  if (!api) throw new Error("wrap the page in <PlaidLinkProvider>")
  return api
}

/** "Link account": opens the pre-initialized Link session. */
export function LinkAccountButton() {
  const { ready, busy, error, link } = useLinkApi()
  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={link} disabled={!ready} className="action-label">
        <Link2 data-icon="inline-start" /> {busy ? "LINKING…" : "LINK ACCOUNT"}
      </Button>
      {error && <p className="text-xs text-muted-foreground">{error}</p>}
    </div>
  )
}

/** "Reconnect": Link update mode for an item whose login broke. Token is fetched on click. */
export function ReconnectButton({ itemId }: { itemId: string }) {
  const { busy, reconnect } = useLinkApi()
  return (
    <Button variant="outline" size="sm" onClick={() => reconnect(itemId)} disabled={busy} className="action-label w-fit">
      <RotateCw data-icon="inline-start" /> RECONNECT
    </Button>
  )
}

/** Re-opens Link after an OAuth bank redirect with the saved link_token and the full return URL. */
export function OAuthResume({ token, itemId, receivedRedirectUri }: LinkSession & { receivedRedirectUri: string }) {
  const router = useRouter()
  const scriptLoaded = usePlaidScript()
  const [failed, setFailed] = useState<string | null>(null)
  const noop = useCallback(() => {}, [])
  const onFinish = useCallback((o: Outcome) => {
    // Any exit here is a dead end (an expired saved token exits with no error), so offer a restart.
    if (o.ok) router.replace("/accounts")
    else setFailed(o.message ?? "The bank connection didn't finish.")
  }, [router])
  if (scriptLoaded === false || failed) {
    return (
      <p className="text-sm text-muted-foreground">
        {failed ?? "Plaid couldn't load."} <Link className="underline" href="/accounts">Start again from Accounts</Link>.
      </p>
    )
  }
  if (!scriptLoaded) return <p className="text-sm text-muted-foreground">Resuming your bank connection…</p>
  return (
    <>
      <p className="text-sm text-muted-foreground">Resuming your bank connection…</p>
      <PlaidHandle token={token} itemId={itemId} autoOpen receivedRedirectUri={receivedRedirectUri} onReady={noop} onBusy={noop} onFinish={onFinish} />
    </>
  )
}
