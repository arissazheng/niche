import type { Metadata } from "next";
import { Cedarville_Cursive, Cormorant_Garamond, Inter_Tight, Reenie_Beanie } from "next/font/google";
import { SiteFooter, SiteHeader } from "@/components/chrome";
import { LiveProvider } from "@/components/live-provider";
import { APP_NAME } from "@/lib/session";
import "./globals.css";

const grotesk = Inter_Tight({ variable: "--font-grotesk", subsets: ["latin"] });
// Moodboard book only: serif for vellum notes, script for headings, handwriting for labels.
const serif = Cormorant_Garamond({ variable: "--font-book-serif", subsets: ["latin"], weight: ["400", "500"], style: ["normal", "italic"] });
const script = Cedarville_Cursive({ variable: "--font-book-script", subsets: ["latin"], weight: "400" });
const hand = Reenie_Beanie({ variable: "--font-book-hand", subsets: ["latin"], weight: "400" });

export const metadata: Metadata = {
  title: APP_NAME,
  description: "Your taste profile, sourced from independent and secondhand sellers.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // Browser extensions inject attributes on <html> before hydration; ignore those (this element only).
    <html lang="en" suppressHydrationWarning>
      <body className={`${grotesk.variable} ${serif.variable} ${script.variable} ${hand.variable} antialiased min-h-dvh flex flex-col`}>
        <LiveProvider>
          <SiteHeader />
          <main className="flex-1">{children}</main>
          <SiteFooter />
        </LiveProvider>
      </body>
    </html>
  );
}
