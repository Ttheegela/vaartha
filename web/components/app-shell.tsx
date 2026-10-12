"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { BarChart3, Bell, Bot, ChevronLeft, ChevronRight, CreditCard, Goal, Home, Landmark, Menu, Newspaper, Settings, TrendingUp, X } from "lucide-react"
import { useState } from "react"
import { AdvisorDrawer } from "@/components/advisor-drawer"
import { Logo } from "@/components/logo"
import { cn } from "@/lib/utils"

const nav = [
  { label: "Home", href: "/", icon: Home }, { label: "Advisor", href: "/advisor", icon: Bot }, { label: "Spending", href: "/spending", icon: BarChart3 },
  { label: "Bills", href: "/bills", icon: CreditCard }, { label: "Investments", href: "/investments", icon: TrendingUp }, { label: "Accounts", href: "/accounts", icon: Landmark },
  { label: "News", href: "/news", icon: Newspaper }, { label: "Goals", href: "/goals", icon: Goal },
]

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname(); const [banner, setBanner] = useState(true); const [collapsed, setCollapsed] = useState(false); const [mobileNav, setMobileNav] = useState(false)
  const navigation = <>{nav.map(({ label, href, icon: Icon }) => <Link key={href} href={href} onClick={() => setMobileNav(false)} className={cn("flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground", pathname === href && "bg-secondary text-foreground")}><Icon className="size-4 shrink-0"/><span className={cn(collapsed && "lg:hidden")}>{label}</span></Link>)}</>
  return <div className="min-h-screen bg-background">
    {banner && <div className="fixed inset-x-0 top-0 z-50 flex h-8 items-center justify-center gap-3 border-b bg-[#101010] px-4 text-[11px] text-muted-foreground"><span>Demo — Plaid Sandbox data, resets nightly. Not financial advice.</span><button onClick={() => setBanner(false)} aria-label="Dismiss demo notice"><X className="size-3.5"/></button></div>}
    <aside className={cn("fixed bottom-0 left-0 z-40 hidden border-r bg-background p-3 transition-all lg:flex lg:flex-col", banner ? "top-8" : "top-0", collapsed ? "w-[76px]" : "w-[220px]")}>
      <div className="flex h-16 items-center justify-between px-3"><Link href="/" aria-label="Vārtā home"><Logo variant={collapsed ? "mark" : "full"} /></Link><button onClick={() => setCollapsed(!collapsed)} className="text-muted-foreground hover:text-foreground" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>{collapsed ? <ChevronRight className="size-4"/> : <ChevronLeft className="size-4"/>}</button></div>
      <nav className="flex flex-col gap-1" aria-label="Main navigation">{navigation}</nav>
      <div className="mt-auto flex flex-col gap-2"><div className={cn("flex items-center gap-2 rounded-xl border px-3 py-2.5", collapsed && "justify-center px-2")}><span className="size-2 rounded-full bg-[#00d89d]"/><span className={cn("font-mono text-[10px] tracking-[.12em] text-[#00d89d]", collapsed && "hidden")}>NORMAL REGIME</span></div><Link href="/settings" className={cn("flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-muted-foreground hover:bg-secondary hover:text-foreground", pathname === "/settings" && "bg-secondary text-foreground")}><Settings className="size-4"/><span className={cn(collapsed && "hidden")}>Settings</span></Link></div>
    </aside>
    <header className={cn("fixed inset-x-0 z-40 flex h-16 items-center justify-between border-b bg-background/90 px-4 backdrop-blur lg:hidden", banner ? "top-8" : "top-0")}><button onClick={() => setMobileNav(true)} aria-label="Open navigation"><Menu className="size-5"/></button><Link href="/" aria-label="Vārtā home"><Logo variant="mark" /></Link><Bell className="size-4 text-muted-foreground"/></header>
    {mobileNav && <div className="fixed inset-0 z-50 bg-background p-4 lg:hidden"><div className="mb-6 flex h-12 items-center justify-between"><Logo variant="full" /><button onClick={() => setMobileNav(false)} aria-label="Close navigation"><X className="size-5"/></button></div><nav className="flex flex-col gap-1">{navigation}<Link href="/settings" className="flex h-11 items-center gap-3 rounded-xl px-3 text-sm text-muted-foreground"><Settings className="size-4"/>Settings</Link></nav></div>}
    <div className={cn("transition-all", collapsed ? "lg:pl-[76px]" : "lg:pl-[220px]", banner ? "pt-24 lg:pt-8" : "pt-16 lg:pt-0")}><main className="mx-auto max-w-[1440px] px-4 py-8 sm:px-6 lg:px-10 lg:py-12">{children}</main></div>
    {pathname !== "/advisor" && <div className="fixed bottom-5 right-5 z-30"><AdvisorDrawer compact/></div>}
  </div>
}
