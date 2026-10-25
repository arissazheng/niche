import Link from "next/link";
import { HeroEnvelope } from "@/components/hero-envelope";

export default function Home() {
  return (
    <div className="px-4">
      {/* Full-width black band with the envelopes (cropped from niche-front.webp) centred on it. */}
      <section className="relative -mx-4 my-4 bg-ink flex flex-col items-center gap-12 py-10">
        <HeroEnvelope />
        <Link href="/onboard" className="text-display bg-paper text-ink px-10 py-4 hover:bg-plinth transition-colors">
          Find your{" "}
          <span className="font-display italic text-[1.01em] leading-none" style={{ fontFeatureSettings: '"swsh" 1, "salt" 1' }}>
            niche
          </span>
        </Link>
      </section>
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
        {[
          ["1", "Tell us", "Answer a few questions out loud or by tapping."],
          ["2", "Show us", "Upload outfits and pieces you love. Click one to say what you like about it."],
          ["3", "Shop for you", "We search independent labels, secondhand and major stores, and explain every match."],
        ].map(([n, title, body]) => (
          <div key={n} className="rule-t pt-1">
            <p className="text-display">{n}</p>
            <p className="text-display mt-6">{title}</p>
            <p className="text-sm mt-1 max-w-xs">{body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
