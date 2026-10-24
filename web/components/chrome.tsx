import Link from "next/link";
import { APP_NAME } from "@/lib/session";

const NAV = [
  { href: "/onboard", label: "Profile" },
  { href: "/upload", label: "Upload" },
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
    <footer className="bg-ink text-paper mt-16 px-4 pt-6 pb-4">
      <a href="#" className="label block text-center">Back to top ↑</a>
      <p className="text-wordmark font-medium tracking-tight text-center my-12">{APP_NAME}</p>
      <div className="label flex flex-wrap justify-between gap-3">
        <span>About</span>
        <span>How ranking works</span>
        <span>Privacy</span>
        <span>Sellers ↗</span>
      </div>
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
