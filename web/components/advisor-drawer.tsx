"use client"

import { MessageCircle, Sparkles } from "lucide-react"
import { AdvisorChat } from "@/components/advisor-chat"
import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet"

export function AdvisorDrawer({ compact = false }: { compact?: boolean }) {
  return <Sheet><SheetTrigger render={<Button className={compact ? "size-12 rounded-full shadow-2xl" : ""} aria-label="Ask Vārtā">{compact ? <MessageCircle/> : <><Sparkles data-icon="inline-start"/>ASK Vārtā →</>}</Button>}/><SheetContent className="w-full border-l bg-background p-0 sm:max-w-[460px]"><SheetHeader className="border-b px-6 py-5"><SheetTitle className="serif-display text-2xl">Vārtā <em>advisor</em></SheetTitle><SheetDescription>Your financial picture, in conversation.</SheetDescription></SheetHeader><AdvisorChat/></SheetContent></Sheet>
}
