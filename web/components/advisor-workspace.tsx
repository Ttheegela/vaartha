"use client"

import { useState } from "react"
import { MessageSquarePlus } from "lucide-react"
import { AdvisorChat, type ChatMessage } from "@/components/advisor-chat"
import { Button } from "@/components/ui/button"
import { relativeTime } from "@/lib/relative-time"
import type { components } from "@/lib/api-types"

type Conversation = components["schemas"]["ConversationOut"]
export function AdvisorWorkspace({ conversations }: { conversations: Conversation[] }) {
  const [list, setList] = useState(conversations); const [active, setActive] = useState<{ key: string; id?: string; initial: ChatMessage[] }>({ key: "new", initial: [] })
  async function open(id: string) {
    const res = await fetch(`/api/conversations/${id}`); if (!res.ok) return
    const rows: components["schemas"]["MessageOut"][] = await res.json()
    setActive({ key: id, id, initial: rows.map((r) => ({ role: r.role === "user" ? "user" : "assistant", text: r.content, sources: r.sources, tools: r.tool_names })) })
  }
  function created(id: string) { setList((l) => l.some((c) => c.id === id) ? l : [{ id, title: "New conversation", updated_at: new Date().toISOString() }, ...l]); setActive((a) => ({ ...a, id })) }
  return <div className="overflow-hidden rounded-[20px] border bg-card lg:grid lg:grid-cols-[280px_1fr]"><aside className="border-b p-4 lg:border-b-0 lg:border-r"><Button variant="outline" className="mb-5 w-full justify-start" onClick={() => setActive({ key: `new-${Date.now()}`, initial: [] })}><MessageSquarePlus data-icon="inline-start"/>NEW CONVERSATION</Button><p className="eyebrow mb-3 px-2">RECENT</p><div className="flex gap-2 overflow-x-auto lg:flex-col">{list.length === 0 && <p className="px-2 text-xs text-muted-foreground">No conversations yet</p>}{list.map((conversation) => <button key={conversation.id} onClick={() => open(conversation.id)} className={`min-w-56 rounded-2xl p-3 text-left hover:bg-secondary lg:min-w-0 ${conversation.id === active.id ? "bg-secondary" : ""}`}><span className="text-sm font-medium">{conversation.title}</span><span className="numeric mt-2 block text-[10px] text-muted-foreground">{relativeTime(conversation.updated_at)}</span></button>)}</div></aside><AdvisorChat key={active.key} full conversationId={active.id} initial={active.initial} onConversation={created}/></div>
}
