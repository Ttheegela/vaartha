import { AdvisorWorkspace } from "@/components/advisor-workspace"
import { apiGet } from "@/lib/server-api"
import type { components } from "@/lib/api-types"

export default async function AdvisorPage() { const conversations = (await apiGet<components["schemas"]["ConversationOut"][]>("/api/conversations")) ?? []; return <div><div className="mb-10"><p className="eyebrow mb-3">YOUR ADVISOR</p><h1 className="serif-display text-4xl lg:text-5xl">Clarity for every <em>decision</em></h1><p className="mt-3 text-sm text-muted-foreground">Ask questions grounded in your complete financial picture.</p></div><AdvisorWorkspace conversations={conversations}/></div> }
