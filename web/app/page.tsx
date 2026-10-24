import Link from "next/link";

const CATEGORIES = ["Outerwear", "Knitwear", "Trousers", "Dresses", "Shoes", "Bags", "Vintage", "Handmade"];

export default function Home() {
  return (
    <div className="px-4">
      <p className="text-display text-center my-2">{CATEGORIES.join(", ")}</p>
      {/* Hero image placeholder: drop the campaign image into /public and swap this block. */}
      <section className="relative bg-plinth aspect-[16/7] w-full">
        <Link href="/onboard" className="label absolute bottom-3 left-1/2 -translate-x-1/2">
          Build your taste profile ↗
        </Link>
      </section>
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
        {[
          ["1", "Tell us", "Answer a few questions out loud or by tapping."],
          ["2", "Show us", "Upload outfits and pieces you love. Click one to say what you like about it."],
          ["3", "Shop small", "We search Etsy, Depop, Poshmark and Grailed and explain every match."],
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
