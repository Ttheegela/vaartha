import type { Metadata } from "next"
import { PasskeyLock } from "@/components/passkey-lock"
import { safeNext } from "@/lib/auth"

export const metadata: Metadata = { title: "Locked" }

/** Owner lock screen. Never redirects on its own, so a web/API config mismatch can't loop. */
export default async function LockPage({ searchParams }: { searchParams: Promise<{ next?: string | string[] }> }) {
  const { next } = await searchParams
  return <PasskeyLock next={safeNext(typeof next === "string" ? next : null)} />
}
