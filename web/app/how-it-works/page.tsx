import Link from "next/link";
import type { Metadata } from "next";
import { SectionTitle } from "@/components/chrome";

export const metadata: Metadata = { title: "How Niche ranks" };

// Plain-language account of sourcing, ranking and data use. Keep it in step with backend/sourcing and backend/taste.

const NEVER_SHOWN = [
  ["Sponsored, promoted or boosted listings", "Dropped before ranking. No seller or store can pay to appear."],
  ["Sizes that clearly don't fit", "If a listing says L and you wear S, it's gone."],
  ["Anything over your price cap", "Your cap is the price you name, or the everyday budget on your profile. Turn on \u201cKeep to budget\u201d in the chat to stay within what's left of your monthly clothing budget."],
  ["Sold or unavailable items", "When the marketplace says so."],
];

const STEPS = [
  ["You ask", "Describe what you want in the chat and Niche searches for it. If a search is Niche's own idea, it asks you first."],
  ["Claude plans the search", "Your request and taste profile become a few concrete search phrases (garment, colour, silhouette)."],
  ["Stores are searched", "Mainstream retailers through Google Shopping, Depop, Poshmark, Vinted and Etsy for secondhand and small shops, and independent labels' own online stores, read directly from their public catalogs."],
  ["Hard filters", "Your size for that kind of garment, your price cap, and the exclusions above."],
  ["Claude looks at each photo", "Every shortlisted listing is compared with your taste profile: colour, silhouette and overall aesthetic, a one-line reason, and caveats."],
  ["Variety", "At most two pieces from the same seller, and when both have good matches, at least a quarter of results each from stores and from secondhand and small shops. Stores and brands you said you like can add up to 10 of 100 points, and only to something that already fits."],
];

const SCAM_CHECKS = [
  "Priced far below the other results for the same search",
  "The listing asks you to pay outside the marketplace (Venmo, Zelle, \u201cDM to buy\u201d), which loses buyer and card protection",
  "The seller has no reviews yet, or a rating under 4 out of 5 (where the marketplace shares ratings: Etsy shops, sometimes Depop)",
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
        <p className="label mt-6 mb-2">What we warn you about</p>
        <ul className="grid gap-1 text-sm">
          {SCAM_CHECKS.map((line) => (
            <li key={line}>— {line}</li>
          ))}
        </ul>
        <p className="text-sm mt-3 text-muted">
          Shown as &ldquo;Before you buy&rdquo; when you open a listing. A warning isn&apos;t proof of a scam, and no
          warning isn&apos;t a guarantee.
        </p>
      </section>

      <section id="data">
        <SectionTitle aside="04">Your data</SectionTitle>
        <div className="grid gap-6 sm:grid-cols-2">
          <div className="grid gap-2 content-start">
            <p className="label">What Niche keeps</p>
            <ul className="grid gap-1 text-sm">
              <li>— Your profile answers: sizes, body measurements if you add them, budget, the shops and brands you like</li>
              <li>— Photos and notes you add to your lookbook, and the taste profile built from them</li>
              <li>— Your searches and their results</li>
              <li>— If you connect a bank (demo): balance, this month&apos;s clothing spend, upcoming bills. Read only; Niche can&apos;t move money.</li>
              <li>— Your chat history stays in this browser</li>
              <li>— If you share your taste: a private link. Anyone with it sees your moodboard (photos, style clusters, palette) and your first name, and can shop for you with your taste and sizes. They never see your sizes, budget, email, age, notes or bank, and their gift searches aren&apos;t added to your history. Stop sharing on your moodboard and the link stops working.</li>
              <li>— If you turn on Shops near you: your ZIP code, sent with each search&apos;s description to Google&apos;s Gemini to find shops on Google Maps</li>
              <li>— If you import a public Pinterest, Instagram or TikTok link, it may be fetched through Bright Data</li>
            </ul>
          </div>
          <div className="grid gap-2 content-start">
            <p className="label">What&apos;s sent to Claude (Anthropic)</p>
            <ul className="grid gap-1 text-sm">
              <li>— Your photos and notes, to build your taste profile</li>
              <li>— Your taste profile, sizes, budget and the conversation, to plan searches and reply</li>
              <li>— Listing photos and details, to rank them for you</li>
              <li>— Your body measurements, if you added them, to check a listing&apos;s stated garment measurements (never used for your taste profile)</li>
              <li>— Your budget summary, if you&apos;ve connected a bank</li>
              <li>— Photos imported from Pinterest, Instagram or TikTok (images only: no account names or captions)</li>
              <li className="font-medium">Never your name, email, age or ZIP code.</li>
            </ul>
          </div>
        </div>
        <p className="text-sm mt-6">
          Niche shows no ads and doesn&apos;t sell your data. Your photos open only through links that expire within two
          hours. You can delete everything from your <Link href="/onboard" className="underline">Profile page</Link>.
        </p>
      </section>

      <Link href="/shop" className="rule-t rule-b text-display py-2 text-center">Start shopping</Link>
    </div>
  );
}
