"use client"
import { useState } from "react"
import { useRouter } from "next/navigation"
import { RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"

export function SyncButton() {
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  async function sync() {
    setBusy(true)
    setNote(null)
    const r = await fetch("/api/sync", { method: "POST" }).catch(() => null)
    setBusy(false)
    if (!r?.ok) return setNote("Sync unavailable")
    const failed = Object.values((await r.json()).items as Record<string, string>).filter((s) => s !== "ok")
    setNote(failed.length ? `${failed.length} account(s) need attention` : null)
    router.refresh()
  }
  return (
    <span className="inline-flex items-center gap-2">
      <Button variant="ghost" size="sm" onClick={sync} disabled={busy}><RefreshCw data-icon="inline-start" className={busy ? "animate-spin" : ""} /> Sync now</Button>
      {note && <span className="text-xs text-muted-foreground">{note}</span>}
    </span>
  )
}
