"use client"

import { FormEvent, useState } from "react"
import { ChevronDown, Send, Sparkles, Wrench } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { cn } from "@/lib/utils"

const prompts = ["What bills are due this week?", "How exposed am I to the current regime?", "Where can I cut subscriptions?", "Am I on track for my emergency fund?"]
export function AdvisorChat({ full = false }: { full?: boolean }) {
  const [messages, setMessages] = useState<{ role: "user" | "assistant"; text: string }[]>([]); const [input, setInput] = useState(""); const [typing, setTyping] = useState(false)
  function ask(text: string) { if (!text.trim()) return; setMessages((m) => [...m, { role: "user", text }]); setInput(""); setTyping(true); window.setTimeout(() => { setMessages((m) => [...m, { role: "assistant", text: "You have 3 bills due in the next 7 days totaling $214.43. Con Edison is the largest at $96.43. Your available cash covers these comfortably, so no transfer is needed." }]); setTyping(false) }, 700) }
  function submit(e: FormEvent) { e.preventDefault(); ask(input) }
  return <div className={cn("flex min-h-0 flex-1 flex-col", full && "min-h-[680px]")}>
    <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-5 sm:p-8" aria-live="polite">
      {messages.length === 0 && <div className="m-auto flex max-w-2xl flex-col items-center gap-6 text-center"><div className="flex size-12 items-center justify-center rounded-full border bg-secondary"><Sparkles className="size-5 text-[#4f8cff]"/></div><div><h2 className="serif-display text-3xl sm:text-4xl">What&apos;s on your <em>mind?</em></h2><p className="mt-3 text-sm leading-6 text-muted-foreground">Ask Vārtā to reason across your cash flow, bills, investments, and goals.</p></div><div className="grid w-full gap-2 sm:grid-cols-2">{prompts.map((prompt) => <button key={prompt} onClick={() => ask(prompt)} className="rounded-2xl border bg-card p-4 text-left text-sm leading-5 hover:bg-secondary">{prompt}</button>)}</div></div>}
      {messages.map((message, index) => <div key={index} className={cn("max-w-[85%] rounded-[20px] p-5 text-sm leading-6", message.role === "user" ? "ml-auto bg-primary text-primary-foreground" : "border bg-card")}><p>{message.text}</p>{message.role === "assistant" && <div className="mt-4 flex flex-col gap-3 border-t pt-4"><Collapsible><CollapsibleTrigger className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[.12em] text-muted-foreground"><Wrench className="size-3.5"/>Used 3 tools<ChevronDown className="size-3.5"/></CollapsibleTrigger><CollapsibleContent className="mt-2 font-mono text-[10px] text-muted-foreground">get_upcoming_bills · get_holdings · get_news</CollapsibleContent></Collapsible><span className="w-fit rounded-full bg-secondary px-3 py-1 text-[11px] text-muted-foreground">[1] Reuters · NVDA export curbs</span></div>}</div>)}
      {typing && <div className="w-fit rounded-[20px] border bg-card px-5 py-4 text-sm text-muted-foreground"><span className="animate-pulse">Reviewing your financial picture…</span></div>}
    </div>
    <form onSubmit={submit} className="p-4 sm:p-6"><div className="flex items-center gap-2 rounded-full border bg-secondary p-2 pl-5 focus-within:border-white/20"><Input value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.nativeEvent.isComposing || e.keyCode === 229)) e.preventDefault() }} className="border-0 bg-transparent shadow-none focus-visible:ring-0" placeholder="Ask anything about your money…" aria-label="Ask Vārtā"/><Button type="submit" size="icon" className="shrink-0 rounded-full"><Send/><span className="sr-only">Send</span></Button></div><p className="mt-3 text-center text-[10px] text-muted-foreground">Educational insights, not financial advice.</p></form>
  </div>
}
