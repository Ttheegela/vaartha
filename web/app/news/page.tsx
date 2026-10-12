import { CrowdOdds, NewsView } from "@/components/news-view"
import { PageHeading } from "@/components/page-heading"
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import type { components } from "@/lib/api-types"
import { toCrowdOdds, toNewsItems } from "@/lib/news-adapters"
import { apiGet } from "@/lib/server-api"

export const dynamic = "force-dynamic"

export default async function NewsPage() {
  const [news, odds] = await Promise.all([
    apiGet<components["schemas"]["NewsItemOut"][]>("/api/news?material_only=false&days=7"),
    apiGet<components["schemas"]["CrowdOddsOut"][]>("/api/crowd_odds"),
  ])
  const items = news ? toNewsItems(news, new Date()) : []
  const oddsRows = odds ? toCrowdOdds(odds) : []
  return (
    <div>
      <PageHeading title="News intelligence" description="Signals ranked by relevance to your holdings." />
      {items.length ? (
        <NewsView items={items} odds={oddsRows} />
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1fr_340px]">
          <Card>
            <CardHeader>
              <CardTitle className="serif-display text-3xl">No <em>news</em> yet</CardTitle>
              <CardDescription>{news ? "Run a news refresh to pull headlines." : "The API isn't reachable right now."}</CardDescription>
            </CardHeader>
          </Card>
          {oddsRows.length > 0 && <aside><CrowdOdds odds={oddsRows} /></aside>}
        </div>
      )}
    </div>
  )
}
