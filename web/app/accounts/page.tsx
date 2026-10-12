import { PageHeading } from "@/components/page-heading"
import { LinkAccountButton } from "@/components/link-account-button"
import { SyncButton } from "@/components/sync-button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { toAccounts } from "@/lib/adapters"
import type { components } from "@/lib/api-types"
import { StatusBadge } from "@/components/status-badge"
import { institutionStatus, itemsWithoutAccounts } from "@/lib/items"
import { relativeTime } from "@/lib/relative-time"
import { apiGet } from "@/lib/server-api"

export const dynamic = "force-dynamic"

const usd = (n: number) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2 })}`

export default async function AccountsPage() {
  const data = await apiGet<components["schemas"]["AccountsOut"]>("/api/accounts")
  const accounts = data ? toAccounts(data) : []
  const institutions = [...new Set(accounts.map((a) => a.institution))]
  const emptyItems = data ? itemsWithoutAccounts(data.items, institutions) : []
  const hasItems = !!data && data.items.length > 0
  return (
    <div>
      <PageHeading
        title="Accounts"
        description="Balances across linked financial institutions."
        action={accounts.length || hasItems ? <div className="flex items-start gap-2"><SyncButton /><LinkAccountButton /></div> : undefined}
      />
      {accounts.length === 0 && !hasItems ? (
        <Card>
          <CardHeader>
            <CardTitle className="serif-display text-3xl">Link your <em>first</em> account</CardTitle>
            <CardDescription>
              {data ? "Vārtā reads balances, transactions and holdings through Plaid. It can't move money." : "The API isn't reachable right now."}
            </CardDescription>
          </CardHeader>
          {data && <CardContent><LinkAccountButton /></CardContent>}
        </Card>
      ) : (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-2">
            <Card><CardHeader><CardTitle className="text-sm text-muted-foreground">Total assets</CardTitle></CardHeader><CardContent><p className="numeric text-3xl">{usd(data!.assets)}</p></CardContent></Card>
            <Card><CardHeader><CardTitle className="text-sm text-muted-foreground">Total liabilities</CardTitle></CardHeader><CardContent><p className="numeric text-3xl text-destructive">{usd(data!.liabilities)}</p></CardContent></Card>
          </div>
          <div className="flex flex-col gap-5">
            {emptyItems.map((it) => (
              <Card key={it.id}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">{it.title}{it.badge && <StatusBadge tone="warning">{it.badge}</StatusBadge>}</CardTitle>
                  <CardDescription>Use Sync now to retry.</CardDescription>
                </CardHeader>
              </Card>
            ))}
            {institutions.map((inst) => {
              const status = institutionStatus(data!.items, inst)
              return (
              <Card key={inst}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">{inst}{status.needsLogin && <StatusBadge tone="warning">Needs re-login</StatusBadge>}</CardTitle>
                  <CardDescription>Linked via Plaid · Last synced <span className="numeric">{relativeTime(status.lastSyncedAt)}</span></CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-1">
                  {accounts.filter((a) => a.institution === inst).map((a) => (
                    <div key={a.id} className="flex items-center gap-4 rounded-lg border bg-background/30 p-4">
                      <div className="flex size-10 items-center justify-center rounded-lg bg-secondary font-mono text-primary">{inst[0]}</div>
                      <div className="min-w-0 flex-1"><p className="font-medium">{a.name}</p><p className="text-xs text-muted-foreground">{a.type} · <span className="numeric">{a.mask}</span></p></div>
                      <p className={a.liability ? "numeric text-lg text-destructive" : "numeric text-lg"}>{a.liability ? "−" : ""}{usd(a.balance)}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}
