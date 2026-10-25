import type { Metadata } from "next";
// Fonts are bundled from npm (@fontsource) rather than fetched from Google Fonts on every dev compile,
// which stalls page loads for minutes on slow networks.
import "@fontsource/inter-tight/400.css";
import "@fontsource/inter-tight/500.css";
import "@fontsource/cormorant-garamond/400.css";
import "@fontsource/cormorant-garamond/400-italic.css";
import "@fontsource/cormorant-garamond/500.css";
import "@fontsource/cormorant-garamond/500-italic.css";
import "@fontsource/cedarville-cursive/400.css";
import "@fontsource/reenie-beanie/400.css";
import "@fontsource/playfair-display/400-italic.css";
import { AssistantDock, AssistantProvider } from "@/components/assistant";
import { SiteFooter, SiteHeader } from "@/components/chrome";
import { LiveProvider } from "@/components/live-provider";
import { ShortlistToast } from "@/components/shortlist";
import { APP_NAME } from "@/lib/session";
import "./globals.css";

export const metadata: Metadata = {
  title: APP_NAME,
  description: "Your taste profile, sourced from independent and secondhand sellers.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    // Browser extensions inject attributes on <html> before hydration; ignore those (this element only).
    <html lang="en" suppressHydrationWarning>
      <body className="antialiased min-h-dvh flex flex-col">
        <LiveProvider>
          {/* The assistant wraps every page, so its conversation carries on as the shopper moves around. */}
          <AssistantProvider>
            <SiteHeader />
            <main className="flex-1 pb-24">{children}</main>
            <SiteFooter />
            <AssistantDock />
            <ShortlistToast />
          </AssistantProvider>
        </LiveProvider>
      </body>
    </html>
  );
}
