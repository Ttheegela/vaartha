"use client"
import { useEffect, useState } from "react"
import { getRegime, type RegimeOut } from "@/lib/api"
import { regimeBadge, type BadgeTone } from "@/lib/regime-badge"
import { cn } from "@/lib/utils"

const TONE_CLASS: Record<BadgeTone, string> = {
  normal: "text-[#00d89d] bg-[#00d89d]",
  elevated: "text-[#e3b341] bg-[#e3b341]",
  crisis: "text-[#f85149] bg-[#f85149]",
  unavailable: "text-muted-foreground bg-muted-foreground",
  loading: "text-muted-foreground bg-muted-foreground",
}

export function RegimePill({ collapsed }: { collapsed: boolean }) {
  const [regime, setRegime] = useState<RegimeOut | null | undefined>(undefined)
  useEffect(() => { getRegime().then(setRegime) }, [])
  const { text, tone } = regimeBadge(regime)
  const [textColor, dotColor] = TONE_CLASS[tone].split(" ")
  return (
    <div className={cn("flex items-center gap-2 rounded-xl border px-3 py-2.5", collapsed && "justify-center px-2")}
      title={text}>
      <span className={cn("size-2 rounded-full", dotColor)} />
      <span className={cn("font-mono text-[10px] tracking-[.12em]", textColor, collapsed && "hidden")}>{text}</span>
    </div>
  )
}
