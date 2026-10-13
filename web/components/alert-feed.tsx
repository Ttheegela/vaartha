"use client"

import { useState } from "react"
import Link from "next/link"
import { X } from "lucide-react"
import { apiUrl } from "@/lib/api-base"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import type { components } from "@/lib/api-types"

type Alert = components["schemas"]["AlertOut"]

/** Dismissible alert list; dismiss is optimistic and restored if the POST fails. */
export function AlertFeed({ initial }: { initial: Alert[] }) {
  const [alerts, setAlerts] = useState(initial)
  async function dismiss(alert: Alert) {
    setAlerts((a) => a.filter((x) => x.id !== alert.id))
    let ok = false
    try { ok = (await fetch(apiUrl(`/api/alerts/${alert.id}/dismiss`), { method: "POST", credentials: "include" })).ok } catch {}
    if (!ok) setAlerts((a) => a.some((x) => x.id === alert.id) ? a : [...a, alert].sort((p, q) => p.id - q.id))
  }
  if (alerts.length === 0) return null
  return <Card><CardHeader><p className="eyebrow">ALERTS</p></CardHeader><CardContent className="flex flex-col">{alerts.map((alert) => <div key={alert.id} className="flex items-center gap-3 border-b py-3 last:border-0"><p className="min-w-0 flex-1 text-sm leading-6">{alert.text}</p>{alert.action_href && alert.action_label && <Link href={alert.action_href} className="shrink-0 text-sm text-[#4f8cff] hover:underline">{alert.action_label}</Link>}<button type="button" aria-label="Dismiss alert" onClick={() => dismiss(alert)} className="shrink-0 rounded-full p-1 text-muted-foreground hover:text-foreground"><X className="size-4"/></button></div>)}</CardContent></Card>
}
