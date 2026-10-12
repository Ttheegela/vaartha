"use client"

import { FormEvent, Fragment, useState } from "react"
import Link from "next/link"
import { ChevronDown, Send, Sparkles, Wrench } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"
import { parseSSE } from "@/lib/sse"
import { splitCitations } from "@/lib/citations"
import type { components } from "@/lib/api-types"

const prompts = ["What bills are due this week?", "How exposed am I to the current regime?", "Where can I cut subscriptions?", "Am I on track for my emergency fund?"]
const UNAVAILABLE = "The advisor is unavailable right now."
type Source = components["schemas"]["SourceOut"]
export type ChatMessage = { role: "user" | "assistant"; text: string; sources?: Source[]; tools?: string[] }
const toolLabel = (name: string) => name.replace(/^get_/, "").replace(/_/g, " ")
export function AdvisorChat({ full = false, conversationId, initial = [], onConversation }: { full?: boolean; conversationId?: string; initial?: ChatMessage[]; onConversation?: (id: string) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>(initial); const [input, setInput] = useState(""); const [busy, setBusy] = useState(false); const [convId, setConvId] = useState(conversationId)
  const patchLast = (patch: Partial<ChatMessage> | ((m: ChatMessage) => Partial<ChatMessage>)) => setMessages((m) => m.map((x, i) => i === m.length - 1 ? { ...x, ...(typeof patch === "function" ? patch(x) : patch) } : x))
  async function ask(text: string) {
    if (!text.trim() || busy) return
    setMessages((m) => [...m, { role: "user", text }, { role: "assistant", text: "", tools: [] }]); setInput(""); setBusy(true)
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text, conversation_id: convId }) })
      if (!res.ok || !res.body) throw new Error("unavailable")
      const reader = res.body.getReader(), decoder = new TextDecoder(); let buf = "", settled = false
      for (;;) {
        const { done, value } = await reader.read(); if (done) break
        const parsed = parseSSE(buf + decoder.decode(value, { stream: true })); buf = parsed.rest
        for (const ev of parsed.events) {
          const d = JSON.parse(ev.data)
          if (ev.event === "meta") { setConvId(d.conversation_id); onConversation?.(d.conversation_id) }
          else if (ev.event === "tool") patchLast((m) => ({ tools: [...(m.tools ?? []), d.name] }))
          else if (ev.event === "answer") { settled = true; patchLast({ text: d.text }) }
          else if (ev.event === "done") patchLast({ sources: d.sources, tools: d.tool_calls.map((t: { name: string }) => t.name) })
          else if (ev.event === "error") { settled = true; patchLast({ text: UNAVAILABLE }) }
        }
      }
      if (!settled) patchLast({ text: UNAVAILABLE })
    } catch { patchLast({ text: UNAVAILABLE }) }
    setBusy(false)
  }
  function submit(e: FormEvent) { e.preventDefault(); ask(input) }
  return <div className={cn("flex min-h-0 flex-1 flex-col", full && "min-h-[680px]")}>
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-5 sm:p-8" aria-live="polite">
      {messages.length === 0 && <div className="m-auto flex max-w-2xl flex-col items-center gap-6 text-center"><div className="flex size-12 items-center justify-center rounded-full border bg-secondary"><Sparkles className="size-5 text-[#4f8cff]"/></div><div><h2 className="serif-display text-3xl sm:text-4xl">What&apos;s on your <em>mind?</em></h2><p className="mt-3 text-sm leading-6 text-muted-foreground">Ask Vārtā to reason across your cash flow, bills, investments, and goals.</p></div><div className="grid w-full gap-2 sm:grid-cols-2">{prompts.map((prompt) => <button key={prompt} onClick={() => ask(prompt)} className="rounded-2xl border bg-card p-4 text-left text-sm leading-5 hover:bg-secondary">{prompt}</button>)}</div></div>}
      {messages.map((message, index) => { const pending = busy && index === messages.length - 1 && !message.text, sources = (message.sources ?? []).filter((s): s is Source & { id: number } => s.id != null), tools = message.tools ?? []
        if (pending) return <div key={index} className="w-fit rounded-[20px] border bg-card px-5 py-4 text-sm text-muted-foreground"><span className="animate-pulse">{tools.length ? `Checking ${toolLabel(tools[tools.length - 1])}…` : "Reviewing your financial picture…"}</span></div>
        return <div key={index} className={cn("max-w-[85%] rounded-[20px] p-5 text-sm leading-6", message.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "border bg-card")}><p>{message.role === "user" ? message.text : splitCitations(message.text, sources).map((seg, i) => seg.kind === "text" ? <Fragment key={i}>{seg.text}</Fragment> : <sup key={i} className="ml-0.5 text-[#4f8cff]">[{seg.n}]</sup>)}</p>{message.role === "assistant" && (tools.length > 0 || sources.length > 0) && <div className="mt-4 flex flex-col gap-3 border-t pt-4">{tools.length > 0 && <Collapsible><CollapsibleTrigger className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[.12em] text-muted-foreground"><Wrench className="size-3.5"/>Used {tools.length} {tools.length === 1 ? "tool" : "tools"}<ChevronDown className="size-3.5"/></CollapsibleTrigger><CollapsibleContent className="mt-2 font-mono text-[10px] text-muted-foreground">{tools.join(" · ")}</CollapsibleContent></Collapsible>}{sources.length > 0 && <div className="flex flex-wrap gap-2">{sources.map((s, i) => <Link key={s.id} href="/news" className="w-fit rounded-full bg-secondary px-3 py-1 text-[11px] text-muted-foreground hover:text-foreground">[{i + 1}] {s.source} · {s.title}</Link>)}</div>}</div>}</div> })}
    </div>
    <form onSubmit={submit} className="p-4 sm:p-6"><div className="flex items-center gap-2 rounded-full border bg-secondary p-2 pl-5 focus-within:border-white/20"><Input disabled={busy} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.nativeEvent.isComposing || e.keyCode === 229)) e.preventDefault() }} className="border-0 bg-transparent shadow-none focus-visible:ring-0" placeholder="Ask anything about your money…" aria-label="Ask Vārtā"/><Button type="submit" disabled={busy} size="icon" className="shrink-0 rounded-full"><Send/><span className="sr-only">Send</span></Button></div><p className="mt-3 text-center text-[10px] text-muted-foreground">Educational insights, not financial advice.</p></form>
  </div>
}
