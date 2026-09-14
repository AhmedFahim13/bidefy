import type { Metadata, Viewport } from "next";
import Link from "next/link";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import "./globals.css";
import { StaleBanner } from "./components/StaleBanner";
import { Sw } from "./components/Sw";
import { API_BASE } from "@/lib/api";

const newsreader = Newsreader({ subsets: ["latin"], variable: "--font-newsreader", axes: ["opsz"] });
const plexSans = IBM_Plex_Sans({ subsets: ["latin"], variable: "--font-plex-sans", weight: ["400", "500", "600"] });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-plex-mono", weight: ["400", "500"] });

export const metadata: Metadata = {
  title: { default: "Bidefy", template: "%s | Bidefy" },
  description: "Tender intelligence for Bangladesh's e-GP portal: live tenders, who wins what, and push alerts.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/icon-192.png" },
  appleWebApp: { capable: true, title: "Bidefy", statusBarStyle: "default" },
};

export const viewport: Viewport = { themeColor: "#2a3a93", width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${newsreader.variable} ${plexSans.variable} ${plexMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <header className="border-b border-rule bg-surface/80 backdrop-blur">
          <div className="mx-auto flex max-w-6xl flex-wrap items-baseline justify-between gap-x-6 gap-y-2 px-4 py-4">
            <Link href="/" className="font-display text-3xl font-semibold tracking-tight text-ink no-underline">
              Bidefy<span className="ml-2 align-middle text-xs font-mono uppercase tracking-[0.16em] text-ink-3">e-GP intelligence</span>
            </Link>
            <nav className="flex gap-6 text-sm font-medium">
              <Link href="/" className="text-ink-2 hover:text-brand">Tenders</Link>
              <Link href="/alerts" className="text-ink-2 hover:text-brand">Alerts</Link>
              <Link href="/access" className="text-ink-2 hover:text-brand">Pro</Link>
              <Link href="/learn" className="text-ink-2 hover:text-brand">Learn</Link>
              <a href={`${API_BASE}/api/v1/health`} className="text-ink-3 hover:text-brand" rel="noreferrer">API</a>
            </nav>
          </div>
        </header>
        <StaleBanner />
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
        <footer className="rule-double mt-16">
          <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-2 px-4 py-6 text-xs text-ink-3">
            <span>Data from eprocure.gov.bd, crawled nightly at one request per second. Zero production cost.</span>
            <span>Derived intelligence, not a mirror of the portal. Flags describe patterns with numbers, never verdicts.</span>
          </div>
        </footer>
        <Sw />
      </body>
    </html>
  );
}
