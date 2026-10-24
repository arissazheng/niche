import Link from "next/link";
import type { Metadata } from "next";
import { SectionTitle } from "@/components/chrome";

export const metadata: Metadata = { title: "How Niche ranks" };

// Plain-language account of sourcing, ranking and data use. Keep it in step with backend/sourcing and backend/taste.

const NEVER_SHOWN = [
  ["Sponsored, promoted or boosted listings", "Dropped before ranking. No seller or store can pay to appear."],
  ["Sizes that clearly don't fit", "If a listing says L and you wear S, it's gone."],
  ["Anything over your price cap", "Your cap is the price you name, or what's left of your monthly clothing budget."],
  ["Sold or unavailable items", "When the marketplace says so."],
];

const STEPS = [
  ["You ask, Niche proposes", "Describe what you want in the chat. Niche suggests a search."],
  ["Claude plans the search", "Your request and taste profile become a few concrete search phrases (garment, colour, silhouette)."],
  ["Stores are searched", "Mainstream retailers through Google Shopping, plus Depop, Poshmark, Vinted and Etsy for secondhand and small shops."],
  ["Hard filters", "Your size for that kind of garment, your price cap, and the exclusions above."],
  ["Claude looks at each photo", "Every shortlisted listing is compared with your taste profile: colour, silhouette and overall aesthetic, a one-line reason, and caveats."],
  ["Variety", "At most two pieces from the same seller, and when both have good matches, at least a quarter of results each from stores and from secondhand and small shops. Stores and brands you said you like can add up to 10 of 100 points, and only to something that already fits."],
];

const CANT_CHECK = [
  "Sizes and condition come from the seller's own listing.",
  "Prices don't include shipping or tax, and we don't verify shipping to you.",
  "Whether a seller is truly small or independent isn't verified.",
  "Listings can sell out between the search and your click.",
  "You buy on the store's own site; Niche never takes payment.",
];

export default function HowItWorks() {
  return (
    <div className="px-4 mt-6 mx-auto max-w-4xl grid gap-12 pb-8">
      <header className="grid gap-2">
        <p className="label">How Niche ranks</p>
        <h1 className="text-wordmark font-medium tracking-tight">No one pays to be here.</h1>
        <p className="text-display max-w-2xl">
          Every result is chosen for how well it fits your taste, size and budget, and comes with the reason why.
        </p>
      </header>

      <section>
        <SectionTitle aside="01">What&apos;s never shown</SectionTitle>
        <dl className="grid gap-3">
          {NEVER_SHOWN.map(([what, why]) => (
            <div key={what} className="grid sm:grid-cols-[18rem_1fr] gap-1 sm:gap-4">
              <dt className="text-sm font-medium">{what}</dt>
              <dd className="text-sm">{why}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section>
        <SectionTitle aside="02">How a piece earns its place</SectionTitle>
        <ol className="grid gap-4">
          {STEPS.map(([title, body], i) => (
            <li key={title} className="grid grid-cols-[3rem_1fr] gap-2">
              <span className="text-display">{i + 1}</span>
              <div>
                <p className="text-sm font-medium">{title}</p>
                <p className="text-sm">{body}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <SectionTitle aside="03">What we can&apos;t check</SectionTitle>
        <ul className="grid gap-1 text-sm">
          {CANT_CHECK.map((line) => (
            <li key={line}>— {line}</li>
          ))}
        </ul>
        <p className="text-sm mt-3 text-muted">These show up as caveats on each result, under &ldquo;Why this matches&rdquo;.</p>
      </section>

      <section id="data">
        <SectionTitle aside="04">Your data</SectionTitle>
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="grid gap-2 content-start">
            <p className="label">What Niche keeps</p>
            <ul className="grid gap-1 text-sm">
              <li>— Your profile answers: sizes, budget, the shops and brands you like</li>
              <li>— Photos and notes you add to your lookbook, and the taste profile built from them</li>
              <li>— Your searches and their results</li>
              <li>— If you connect a bank (demo): balance, this month&apos;s clothing spend, upcoming bills. Read only; Niche can&apos;t move money.</li>
              <li>— Your chat history stays in this browser</li>
              <li>— If you import a public Pinterest board or Instagram profile, its link is fetched through Bright Data</li>
            </ul>
          </div>
          <div className="grid gap-2 content-start">
            <p className="label">What&apos;s sent to Claude (Anthropic)</p>
            <ul className="grid gap-1 text-sm">
              <li>— Your photos and notes, to build your taste profile</li>
              <li>— Your taste profile, sizes, budget and the conversation, to plan searches and reply</li>
              <li>— Listing photos and details, to rank them for you</li>
              <li>— Your budget summary, if you&apos;ve connected a bank</li>
              <li>— Photos imported from Pinterest or Instagram (photos only: no account names or captions)</li>
              <li className="font-medium">Never your name, email or age.</li>
            </ul>
          </div>
        </div>
        <p className="text-sm mt-6">
          Niche shows no ads and doesn&apos;t sell your data.{" "}
          <span className="text-muted">
            Demo limitation: there are no accounts yet, so uploaded photos can be opened by anyone who has their link.
          </span>
        </p>
      </section>

      <Link href="/shop" className="rule-t rule-b text-display py-2 text-center">Start shopping</Link>
    </div>
  );
}
