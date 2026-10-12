import Link from "next/link"
import { BillsView } from "@/components/bills-view"
import { PageHeading } from "@/components/page-heading"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { toBills } from "@/lib/adapters"
import type { components } from "@/lib/api-types"
import { apiGet } from "@/lib/server-api"

export const dynamic = "force-dynamic"

export default async function BillsPage() {
  const data = await apiGet<components["schemas"]["RecurringListOut"]>("/api/recurring")
  const now = new Date()
  const bills = data ? toBills(data, now) : []
  return (
    <div>
      <PageHeading title="Your bills" description="See what is coming, what changed, and where you can save." />
      {bills.length ? (
        <BillsView bills={bills} month={now} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="serif-display text-3xl">No <em>bills</em> yet</CardTitle>
            <CardDescription>
              {data ? <>Link an account and Vārtā will find your subscriptions and bills. <Link href="/accounts" className="underline underline-offset-4">Go to accounts</Link></> : "The API isn't reachable right now."}
            </CardDescription>
          </CardHeader>
        </Card>
      )}
    </div>
  )
}
