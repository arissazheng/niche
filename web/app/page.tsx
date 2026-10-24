import Image from "next/image";
import Link from "next/link";

const CATEGORIES = ["Outerwear", "Knitwear", "Trousers", "Dresses", "Shoes", "Bags", "Vintage", "Handmade"];

export default function Home() {
  return (
    <div className="px-4">
      <p className="text-display text-center my-2">{CATEGORIES.join(", ")}</p>
      {/* Full-width black band with the envelopes (cropped from niche-front.webp) centred on it. */}
      <section className="relative -mx-4 my-4 bg-ink flex flex-col items-center gap-6 py-10">
        <Image
          src="/niche-front-envelopes.webp"
          alt="Niche"
          width={802}
          height={708}
          priority
          className="h-[60dvh] min-h-[320px] w-auto max-w-[92%] object-contain"
        />
        <Link href="/onboard" className="label bg-paper text-ink px-6 py-3">
          Find your niche
        </Link>
      </section>
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
        {[
          ["1", "Tell us", "Answer a few questions out loud or by tapping."],
          ["2", "Show us", "Upload outfits and pieces you love. Click one to say what you like about it."],
          ["3", "Shop small", "We search independent labels, secondhand and major stores, and explain every match."],
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
