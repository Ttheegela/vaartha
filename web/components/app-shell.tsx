"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { BarChart3, Bell, Bot, ChevronLeft, ChevronRight, CreditCard, Goal, Home, Landmark, Lock, Menu, Newspaper, Settings, TrendingUp, X } from "lucide-react"
import { useEffect, useState } from "react"
import { AdvisorDrawer } from "@/components/advisor-drawer"
import { Logo } from "@/components/logo"
import { RegimePill } from "@/components/regime-pill"
import { apiUrl } from "@/lib/api-base"
import { LOCK_PATH, lockPath } from "@/lib/auth"
import { createIdleTimer, IDLE_CHECK_MS, IDLE_TIMEOUT_MS, isLockEvent, markLocked, storageStore } from "@/lib/idle"
import { cn } from "@/lib/utils"

const nav = [
  { label: "Home", href: "/", icon: Home }, { label: "Advisor", href: "/advisor", icon: Bot }, { label: "Spending", href: "/spending", icon: BarChart3 },
  { label: "Bills", href: "/bills", icon: CreditCard }, { label: "Investments", href: "/investments", icon: TrendingUp }, { label: "Accounts", href: "/accounts", icon: Landmark },
  { label: "News", href: "/news", icon: Newspaper }, { label: "Goals", href: "/goals", icon: Goal },
]
const ACTIVITY_EVENTS = ["pointerdown", "pointermove", "keydown", "scroll", "wheel", "touchstart"]

/** End the session server-side, then show the lock screen (returning here after unlock).
 * False if the logout didn't go through: then the session is still live, so don't pretend it's locked. */
async function lockNow(): Promise<boolean> {
  const res = await fetch(apiUrl("/api/auth/logout"), { method: "POST", credentials: "include", keepalive: true }).catch(() => null)
  if (!res?.ok) return false
  markLocked(sharedStorage(), Date.now()) // other tabs share this session: lock them too
  window.location.assign(lockPath(window.location.pathname + window.location.search))
  return true
}

function sharedStorage(): Storage | null {
  try { return window.localStorage } catch { return null }
}

export function AppShell({ children, demo, auth }: { children: React.ReactNode; demo: boolean; auth: boolean }) {
  const pathname = usePathname(); const [banner, setBanner] = useState(demo); const [collapsed, setCollapsed] = useState(false); const [mobileNav, setMobileNav] = useState(false)
  const locked = pathname === LOCK_PATH
  const [lockFailed, setLockFailed] = useState(false)
  const lock = () => lockNow().then((ok) => setLockFailed(!ok))
  useEffect(() => {
    if (!auth || locked) return
    // Shared across tabs: one session, so a background tab must not log out an active one.
    const timer = createIdleTimer({ timeoutMs: IDLE_TIMEOUT_MS, now: Date.now, store: storageStore(sharedStorage), onIdle: () => { lockNow().then((ok) => setLockFailed(!ok)) } })
    const reset = () => timer.reset()
    // Timers are throttled in hidden tabs and paused in sleep: check elapsed time on return first.
    const onVisibility = () => { if (document.visibilityState === "visible") { timer.check(); timer.reset() } }
    ACTIVITY_EVENTS.forEach((e) => window.addEventListener(e, reset, { capture: true, passive: true }))
    document.addEventListener("visibilitychange", onVisibility)
    const id = window.setInterval(() => timer.check(), IDLE_CHECK_MS)
    const onStorage = (e: StorageEvent) => { if (isLockEvent(e)) window.location.assign(lockPath(window.location.pathname + window.location.search)) }
    window.addEventListener("storage", onStorage)
    return () => {
      window.removeEventListener("storage", onStorage)
      timer.stop(); window.clearInterval(id); document.removeEventListener("visibilitychange", onVisibility)
      ACTIVITY_EVENTS.forEach((e) => window.removeEventListener(e, reset, { capture: true }))
    }
  }, [auth, locked])
  if (locked) return <main className="min-h-screen bg-background">{children}</main> // no nav, no data fetches
  const lockButton = auth && <button onClick={lock} aria-label="Lock Vārtā" className="flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground"><Lock className="size-4"/><span className={cn(collapsed && "lg:hidden")}>Lock</span></button>
  const navigation = <>{nav.map(({ label, href, icon: Icon }) => <Link key={href} href={href} onClick={() => setMobileNav(false)} className={cn("flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground", pathname === href && "bg-secondary text-foreground")}><Icon className="size-4 shrink-0"/><span className={cn(collapsed && "lg:hidden")}>{label}</span></Link>)}</>
  return <div className="min-h-screen bg-background">
    {lockFailed && <div role="alert" className="fixed inset-x-0 top-0 z-[60] flex h-10 items-center justify-center gap-3 border-b bg-[#2a1212] px-4 text-xs text-foreground"><span>Couldn&apos;t lock: Vārtā didn&apos;t confirm the logout.</span><button className="underline" onClick={lock}>Try again</button></div>}
    {banner && <div className="fixed inset-x-0 top-0 z-50 flex h-8 items-center justify-center gap-3 border-b bg-[#101010] px-4 text-[11px] text-muted-foreground"><span>Demo — Plaid Sandbox data, resets nightly. Not financial advice.</span><button onClick={() => setBanner(false)} aria-label="Dismiss demo notice"><X className="size-3.5"/></button></div>}
    <aside className={cn("fixed bottom-0 left-0 z-40 hidden border-r bg-background p-3 transition-all lg:flex lg:flex-col", banner ? "top-8" : "top-0", collapsed ? "w-[76px]" : "w-[220px]")}>
      <div className="flex h-16 items-center justify-between px-3"><Link href="/" aria-label="Vārtā home"><Logo variant={collapsed ? "mark" : "full"} /></Link><button onClick={() => setCollapsed(!collapsed)} className="text-muted-foreground hover:text-foreground" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>{collapsed ? <ChevronRight className="size-4"/> : <ChevronLeft className="size-4"/>}</button></div>
      <nav className="flex flex-col gap-1" aria-label="Main navigation">{navigation}</nav>
      <div className="mt-auto flex flex-col gap-2"><RegimePill collapsed={collapsed} /><Link href="/settings" className={cn("flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground", pathname === "/settings" && "bg-secondary text-foreground")}><Settings className="size-4"/><span className={cn(collapsed && "hidden")}>Settings</span></Link>{lockButton}</div>
    </aside>
    <header className={cn("fixed inset-x-0 z-40 flex h-16 items-center justify-between border-b bg-background/90 px-4 backdrop-blur lg:hidden", banner ? "top-8" : "top-0")}><button onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu className="size-5"/></button><Link href="/" aria-label="Vārtā home"><Logo variant="mark" /></Link><Bell className="size-4 text-muted-foreground"/></header>
    {mobileNav && <div className="fixed inset-0 z-50 bg-background p-4 lg:hidden"><div className="mb-6 flex h-12 items-center justify-between"><Logo variant="full" /><button onClick={() => setMobileNav(false)} aria-label="Close navigation"><X className="size-5"/></button></div><nav className="flex flex-col gap-1">{navigation}<Link href="/settings" className="flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-muted-foreground"><Settings className="size-4"/>Settings</Link>{lockButton}</nav></div>}
    <div className={cn("transition-all", collapsed ? "lg:pl-[76px]" : "lg:pl-[220px]", banner ? "pt-24 lg:pt-8" : "pt-16 lg:pt-0")}><main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-10 lg:py-12">{children}</main></div>
    {pathname !== "/advisor" && <div className="fixed bottom-5 right-5 z-30"><AdvisorDrawer compact/></div>}
  </div>
}
