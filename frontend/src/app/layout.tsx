import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { LocalEnvBanner } from "@/components/LocalEnvBanner";
import Link from "next/link";
import { Toaster } from "@/components/ui/toaster";
import Image from "next/image";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Investment Analytics",
  description: "Stock Viewer & Portfolio Builder",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen flex flex-col text-base`}
      >
        <LocalEnvBanner />
        <header className="sticky top-0 z-40 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="container flex h-16 items-center justify-between px-4">
            <div className="flex items-center gap-6 md:gap-10">
              <Link href="/" className="flex items-center gap-3">
                <Image
                  src="/agent-avatar.png"
                  alt="InvestAnalytics Mascot"
                  width={40}
                  height={40}
                  className="rounded-full"
                />
                <span className="font-extrabold text-xl tracking-tight text-primary">InvestAnalytics</span>
              </Link>
              <nav className="flex gap-6">
                <Link
                  href="/"
                  className="flex items-center text-base font-semibold text-muted-foreground transition-colors hover:text-primary"
                >
                  Dashboard
                </Link>
                <Link
                  href="/portfolio"
                  className="flex items-center text-base font-semibold text-muted-foreground transition-colors hover:text-primary"
                >
                  Portfolio Builder
                </Link>
              </nav>
            </div>
            <div className="flex flex-1 items-center justify-end space-x-4">
              {/* Removed GlobalSearch */}
            </div>
          </div>
        </header>
        <main className="flex-1 container mx-auto px-4 py-6">
          {children}
        </main>
        <Toaster />
      </body>
    </html>
  );
}
