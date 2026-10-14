"use client"
import { useEffect, useState } from "react"
import Link from "next/link"
import { PageHeading } from "@/components/page-heading"
import { OAuthResume } from "@/components/link-account-button"
import { loadLinkSession, type LinkSession } from "@/lib/plaid-link"

/** Plaid OAuth redirect target (register this exact https URL in the Plaid Dashboard). */
export default function OAuthReturnPage() {
  const [state, setState] = useState<{ session: LinkSession | null; url: string } | null>(null)
  useEffect(() => {
    let storage: Storage | null = null
    try { storage = window.localStorage } catch { /* blocked */ }
    setState({ session: loadLinkSession(storage), url: window.location.href })
  }, [])
  return (
    <div>
      <PageHeading title="Connecting your bank" description="Finishing the secure handoff from your bank." />
      {state && !state.session ? (
        <p className="text-sm text-muted-foreground">This bank connection expired or was opened in another browser. <Link className="underline" href="/accounts">Start again from Accounts</Link>.</p>
      ) : state?.session ? (
        <OAuthResume token={state.session.token} itemId={state.session.itemId} receivedRedirectUri={state.url} />
      ) : null}
    </div>
  )
}
