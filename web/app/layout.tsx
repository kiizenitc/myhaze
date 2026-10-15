import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Footer } from "@/components/Footer";

import "./globals.css";

export const metadata: Metadata = {
  title: "MYHaze: haze Real Feel for Malaysian parents",
  description: "Hour-by-hour haze forecast for the next 48 hours at every DOE air-quality station in Malaysia.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <header className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <Link href="/" className="text-xl font-semibold">MYHaze</Link>
          <nav className="flex gap-4 text-[15px] text-[var(--ink-2)]">
            <Link href="/stations/">Stations</Link>
            <Link href="/map/">Map</Link>
            <Link href="/about/">About</Link>
          </nav>
        </header>
        <main className="mx-auto max-w-3xl px-4 pb-10">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
