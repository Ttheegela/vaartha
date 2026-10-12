import type { Metadata, Viewport } from "next"
import { IBM_Plex_Mono, Instrument_Serif, Inter } from "next/font/google"
import { AppShell } from "@/components/app-shell"
import "./globals.css"

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" })
const instrumentSerif = Instrument_Serif({ subsets: ["latin", "latin-ext"], variable: "--font-instrument-serif", weight: "400", style: ["normal", "italic"] })
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-plex-mono", weight: ["400", "500", "600"] })

export const metadata: Metadata = { title: { default: "Vārtā — your proactive financial advisor", template: "%s · Vārtā" }, description: "A calm, proactive personal finance and investing advisor." }
export const viewport: Viewport = { colorScheme: "dark", themeColor: "#0a0a0a", userScalable: true }

export const dynamic = "force-dynamic" // VARTA_INSTANCE is read per request, not frozen at build

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className={`dark bg-background ${inter.variable} ${instrumentSerif.variable} ${plexMono.variable}`}><body className="min-h-screen antialiased"><AppShell demo={process.env.VARTA_INSTANCE === "demo"}>{children}</AppShell></body></html>
}
