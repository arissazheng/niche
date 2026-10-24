import Link from "next/link";
import { APP_NAME } from "@/lib/session";

const NAV = [
  { href: "/onboard", label: "Profile" },
  { href: "/upload", label: "Lookbook" },
  { href: "/taste", label: "Taste" },
  { href: "/shop", label: "Shop" },
];

export function SiteHeader() {
  return (
    <header>
      <div className="bg-ink text-paper label py-2 text-center">
        Major retailers, small shops &amp; secondhand — no sponsored placements
      </div>
      <nav className="label flex justify-center gap-4 py-2">
        <Link href="/">{APP_NAME}</Link>
        {NAV.map((item) => (
          <Link key={item.href} href={item.href} className="hover:underline">
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

export function SiteFooter() {
  return (
    <footer className="bg-ink text-paper mt-16 px-4 pt-6 overflow-hidden">
      <div className="label flex justify-between gap-4">
        <a href="#">Back to top ↑</a>
        <Link href="/how-it-works">Ranking &amp; privacy</Link>
      </div>
      {/* Edge-to-edge wordmark in swash italic, its descenders cut by the bottom of the page. */}
      <p
        aria-hidden
        className="font-display italic text-center leading-[0.95] tracking-[-0.02em] text-[41vw] -mb-[4.5vw] mt-2 whitespace-nowrap select-none"
        style={{ fontFeatureSettings: '"swsh" 1, "salt" 1' }}
      >
        {APP_NAME}
      </p>
    </footer>
  );
}

/** Numbered caption under a tile, like the "1  2  /4" indices in the reference. */
export function Index({ n, total }: { n: number; total?: number }) {
  return <span className="text-display">{total ? `/${total}` : n}</span>;
}

export function SectionTitle({ children, aside }: { children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="rule-t flex items-baseline justify-between pt-1 mb-3">
      <h2 className="text-display">{children}</h2>
      {aside && <span className="label">{aside}</span>}
    </div>
  );
}
