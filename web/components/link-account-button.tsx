"use client"
import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { usePlaidLink } from "react-plaid-link"
import { Link2 } from "lucide-react"
import { Button } from "@/components/ui/button"

export function LinkAccountButton() {
  const router = useRouter()
  const [token, setToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch("/api/plaid/link_token", { method: "POST" })
      .then(async (r) => (r.ok ? setToken((await r.json()).link_token) : setError("Account linking is unavailable")))
      .catch(() => setError("Account linking is unavailable"))
  }, [])

  const onSuccess = useCallback(async (publicToken: string | null) => {
    if (!publicToken) return
    setBusy(true)
    const r = await fetch("/api/plaid/exchange", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ public_token: publicToken }),
    }).catch(() => null)
    setBusy(false)
    if (r?.ok) router.refresh()
    else setError("Couldn't link that account. Try again.")
  }, [router])

  const { open, ready } = usePlaidLink({ token, onSuccess })
  return (
    <div className="flex flex-col items-end gap-1">
      <Button onClick={() => open()} disabled={!ready || busy} className="action-label">
        <Link2 data-icon="inline-start" /> {busy ? "LINKING…" : "LINK ACCOUNT"}
      </Button>
      {error && <p className="text-xs text-muted-foreground">{error}</p>}
    </div>
  )
}
