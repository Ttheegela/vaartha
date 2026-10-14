"use client"
import { useEffect, useState } from "react"
import { startAuthentication, startRegistration } from "@simplewebauthn/browser"
import { Fingerprint, KeyRound } from "lucide-react"
import { Logo } from "@/components/logo"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { apiUrl } from "@/lib/api-base"
import { ceremonyErrorMessage } from "@/lib/auth"

const SETUP_CODE_MAX = 9 // 8 characters, optionally shown as XXXX-XXXX

type CeremonyError = { name?: string; code?: string; status?: number }

async function post(path: string, body?: unknown): Promise<Response> {
  const res = await fetch(apiUrl(path), {
    method: "POST", credentials: "include",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status })
  return res
}

/** Unlock with a passkey, or register one with a CLI setup code; then load `next`. */
export function PasskeyLock({ next }: { next: string }) {
  const [setup, setSetup] = useState(false)
  const [hasPasskey, setHasPasskey] = useState(true)
  const [noLock, setNoLock] = useState(false)
  const [code, setCode] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(apiUrl("/api/auth/status"), { credentials: "include" })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error())))
      .then((s: { auth_required: boolean; has_credentials: boolean }) => {
        if (!s.auth_required) return setNoLock(true)
        setHasPasskey(s.has_credentials); if (!s.has_credentials) setSetup(true)
      })
      .catch(() => setError("Vārtā isn't reachable right now. Is it running on your Mac?"))
  }, [])

  async function run(ceremony: () => Promise<void>) {
    setBusy(true); setError(null)
    try {
      await ceremony()
      window.location.assign(next) // full load so server pages fetch with the new cookie
    } catch (e) {
      const err = e as CeremonyError
      setError(ceremonyErrorMessage(err, hasPasskey))
      setBusy(false)
    }
  }

  const unlock = () => run(async () => {
    const optionsJSON = await (await post("/api/auth/login/options")).json()
    const credential = await startAuthentication({ optionsJSON })
    await post("/api/auth/login/verify", { credential })
  })

  const register = () => run(async () => {
    const optionsJSON = await (await post("/api/auth/register/options", { setup_code: code })).json()
    const credential = await startRegistration({ optionsJSON })
    await post("/api/auth/register/verify", { setup_code: code, credential })
  })

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
        <Logo variant="full" />
        {noLock ? (
          <p className="text-sm text-muted-foreground">This instance has no lock. <a className="underline" href="/">Go home</a></p>
        ) : !setup ? (
          <>
            <p className="text-sm text-muted-foreground">Vārtā is locked.</p>
            <Button size="lg" className="w-full" onClick={unlock} disabled={busy}><Fingerprint data-icon="inline-start" />Unlock with Touch ID</Button>
          </>
        ) : (
          <form className="flex w-full flex-col gap-3" onSubmit={(e) => { e.preventDefault(); register() }}>
            <p className="font-medium">Set up your passkey</p>
            <label className="text-xs text-muted-foreground" htmlFor="setup-code">
              Run <code className="font-mono">uv run python -m scripts.passkey setup-code</code> on your Mac and enter the code.
            </label>
            <Input id="setup-code" value={code} onChange={(e) => setCode(e.target.value)} maxLength={SETUP_CODE_MAX}
              autoComplete="one-time-code" autoCapitalize="characters" spellCheck={false} placeholder="XXXX-XXXX" className="text-center font-mono tracking-widest" />
            <Button size="lg" type="submit" disabled={busy || code.replace(/[-\s]/g, "").length !== 8}><KeyRound data-icon="inline-start" />Create passkey</Button>
          </form>
        )}
        {error && <p role="alert" className="text-sm text-muted-foreground">{error}</p>}
        {hasPasskey && !noLock && (
          <button className="text-xs text-muted-foreground underline" onClick={() => { setSetup(!setup); setError(null) }}>
            {setup ? "Unlock with an existing passkey" : "Set up a passkey on this device"}
          </button>
        )}
      </div>
    </div>
  )
}
