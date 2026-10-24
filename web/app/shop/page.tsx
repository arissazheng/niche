"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useSpacetimeDB, useTable } from "spacetimedb/react";
import { Checkout } from "@/components/checkout";
import { SectionTitle } from "@/components/chrome";
import { Drawer } from "@/components/drawer";
import { api } from "@/lib/api";
import { useAssistant } from "@/lib/assistant";
import { tables } from "@/lib/spacetime";
import { TIER_LABELS, type Budget, type Listing, type NearbyShops, type SearchCounts, type SearchJob } from "@/lib/types";

const DONE = new Set(["completed", "partial", "failed", "interrupted"]);
// Tap-to-ask starters before the first search; the assistant (bottom of every page) does the talking.
const STARTERS = ["Find me black knee-high boots under $120", "Find me a vintage leather jacket", "I need an outfit for a wedding"];

export default function ShopPage() {
  const assistant = useAssistant();
  const { profileId, searchId, budget, keepToBudget, setKeepToBudget, refreshBudget, reset, announce, fresh } = assistant.shop;
  const [job, setJob] = useState<SearchJob | null>(null);
  const [selected, setSelected] = useState<Listing | null>(null);
  const [kind, setKind] = useState<Kind>("all");
  const [error, setError] = useState<string | null>(null);
  const pollToken = useRef(0);
  const announced = useRef(fresh);
  announced.current = fresh;

  // Listings stream in from SpacetimeDB as each marketplace returns; ranking then reorders them in place.
  const { isActive } = useSpacetimeDB();
  const [liveRows] = useTable(tables.listing.where((r) => r.searchId.eq(searchId ?? "")), { enabled: !!searchId });
  const [liveSearch] = useTable(tables.search.where((r) => r.searchId.eq(searchId ?? "")), { enabled: !!searchId });
  const liveListings: Listing[] = [...liveRows]
    .sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9))
    .map((r) => ({
      id: r.listingId,
      source: r.source as Listing["source"],
      title: r.title,
      url: r.url,
      image_urls: r.imageUrl ? [r.imageUrl] : [],
      price: r.price,
      currency: r.currency,
      seller: r.seller || null,
      retailer: r.retailer || null,
      tier: (r.tier || null) as Listing["tier"],
      brand: r.brand || null,
      condition: null,
      sizes: [],
      warnings: r.warnings,
      score: r.score ?? null,
      reason: r.reason,
      is_fixture: r.isFixture,
    }));

  // Follows the assistant's current search to completion. A newer search bumps the token, which stops older loops.
  useEffect(() => {
    const token = ++pollToken.current;
    setJob(null);
    setError(null);
    if (!searchId) return;
    (async () => {
      try {
        for (;;) {
          const next = await api.getSearch(`/v1/searches/${searchId}`);
          if (token !== pollToken.current) return;
          setJob(next);
          if (DONE.has(next.status)) {
            // A search started in this visit: the assistant tells the shopper what came back.
            if (announced.current) announce(searchId, resultsLine(next));
            return;
          }
          // The live subscription drives the page; polling picks up the final record (faster if live is down).
          await new Promise((r) => setTimeout(r, isActive ? 4000 : 1500));
        }
      } catch (err) {
        if (token === pollToken.current) setError((err as Error).message);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- one loop per search
  }, [searchId]);

  if (!profileId) {
    return (
      <p className="px-4 mt-10 text-display">
        Build your <Link href="/onboard" className="underline">taste profile</Link> first.
      </p>
    );
  }

  const finished = !!job && DONE.has(job.status);
  const allResults = finished ? job.results ?? [] : liveListings.length ? liveListings : job?.results ?? [];
  const results = kind === "all" ? allResults : allResults.filter((item) => kindOf(item) === kind);
  const status = finished ? job.status : liveSearch[0]?.status ?? job?.status;
  const ranked = finished || liveRows.some((r) => r.rank !== undefined);

  return (
    <div className="px-4 mt-6 grid gap-4">
      {budget?.linked && <BudgetStrip budget={budget} keepToBudget={keepToBudget} onToggle={setKeepToBudget} />}
      <section className="min-w-0">
        {!searchId ? (
          <div className="rule-t pt-2 grid gap-4 justify-items-start">
            <p className="text-display">Tell Niche what you&apos;re looking for.</p>
            <p className="text-sm max-w-md">
              Talk or type at the bottom of the page, then keep going: &ldquo;less formal&rdquo;, &ldquo;only black&rdquo;,
              &ldquo;under $60&rdquo;. Each reply refines the search.
            </p>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => assistant.start("voice")} className="label bg-ink text-paper px-3 py-1.5">
                Talk to Niche
              </button>
              {STARTERS.map((text) => (
                <button key={text} onClick={() => assistant.send(text)} className="label border border-ink px-3 py-1.5 text-left">
                  {text}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <SectionTitle
              aside={
                <span className="flex gap-3">
                  {job?.ranking_method}
                  <button onClick={reset} className="underline">New search</button>
                </span>
              }
            >
              {matchCount(results.length, !finished)}
            </SectionTitle>
            <p className="label mb-3">
              No sponsored results · ranked by fit to your taste, size and budget ·{" "}
              <Link href="/how-it-works" className="underline">How ranking works</Link>
            </p>
            {finished && job.counts && <Impact counts={job.counts} results={allResults} />}
            <MixFilter results={allResults} kind={kind} onChange={setKind} />
            {status && !DONE.has(status) && (
              <p className="label mb-3 animate-pulse">
                {results.length
                  ? `${ranked ? "Ranking" : "Comparing them to your taste"}…`
                  : "Searching stores and secondhand sellers, then checking each photo against your request…"}
              </p>
            )}
            {error && <p className="text-sm mb-2">{error}</p>}
            {job?.warnings?.map((w) => (
              <p key={w} className="label mb-2 text-muted">{w}</p>
            ))}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
              {results.map((item, i) => (
                <button key={item.id} onClick={() => setSelected(item)} className="text-left">
                  <div className="bg-plinth aspect-[3/4] flex items-center justify-center overflow-hidden">
                    {item.image_urls[0] ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.image_urls[0]} alt="" className="h-full w-full object-contain" />
                    ) : (
                      <span className="label text-muted">{item.is_fixture ? "Demo item" : "No photo"}</span>
                    )}
                  </div>
                  <div className="flex justify-between mt-1 gap-2">
                    <span className="text-display">{i + 1}</span>
                    <span className="label pt-1 text-right">{storeLabel(item)}</span>
                  </div>
                  <p className="text-sm">{item.title}</p>
                  <p className="text-sm">{item.price.toFixed(2)} {item.currency}</p>
                </button>
              ))}
            </div>
            {/* Looked up alongside the search and shown as soon as it's ready (it sits below the listings). */}
            <NearbyShopsSection key={searchId} profileId={profileId} searchId={searchId} show={results.length > 0} />
          </>
        )}
      </section>

      <Drawer open={!!selected} onClose={() => setSelected(null)}>
        {selected && searchId && (
          <ListingDetail listing={selected} searchId={searchId} onPurchased={refreshBudget} />
        )}
      </Drawer>
    </div>
  );
}

/** What the assistant says when a search finishes: how many, and the top pick. */
function resultsLine(job: SearchJob) {
  const results = job.results ?? [];
  if (!results.length) return "Hmm, nothing came back for that one. Want to try it a different way?";
  const top = results[0];
  const store = top.retailer ?? top.seller ?? "";
  return `Found ${results.length} ${results.length === 1 ? "piece" : "pieces"}! My top pick is number 1, ${top.title}${
    store ? ` from ${store}` : ""
  } for $${Math.round(top.price)}. Want me to compare a few, or tweak the search?`;
}

const money = (n = 0) => `$${Math.round(n).toLocaleString()}`;
const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** "$95 of $150 clothing this month · $55 left" plus the next bill, from the shopper's mock bank. */
function BudgetStrip({
  budget,
  keepToBudget,
  onToggle,
}: {
  budget: Budget;
  keepToBudget: boolean;
  onToggle: (on: boolean) => void;
}) {
  const spent = budget.month_spent ?? 0;
  const limit = budget.monthly_budget ?? 0;
  const used = limit ? Math.min(100, (spent / limit) * 100) : 0;
  const bill = budget.upcoming_bills?.[0];
  return (
    <div className="border border-ink px-3 py-2 grid gap-1" title="From your linked Capital One (Nessie) demo account">
      <div className="flex justify-between label">
        <span>
          {money(spent)} of {money(limit)} clothing this month
        </span>
        <span>{money(budget.remaining)} left</span>
      </div>
      <div className="h-1 bg-plinth">
        <div className="h-full bg-ink" style={{ width: `${used}%` }} />
      </div>
      <div className="flex items-center justify-between gap-2">
        <p className="label text-muted">
          Balance {money(budget.balance)}
          {bill && ` · ${bill.payee} ${money(bill.amount)} due ${shortDate(bill.due)}`}
        </p>
        <button
          type="button"
          role="switch"
          aria-checked={keepToBudget}
          onClick={() => onToggle(!keepToBudget)}
          className={`label border border-ink px-2 py-0.5 shrink-0 ${keepToBudget ? "bg-ink text-paper" : ""}`}
          title="When on, searches stay within what's left of your monthly clothing budget"
        >
          Keep to budget: {keepToBudget ? "on" : "off"}
        </button>
      </div>
    </div>
  );
}

/** Opt-in local shops for this search, from Gemini with Google Maps; hidden when off or unavailable. */
function NearbyShopsSection({ profileId, searchId, show }: { profileId: string; searchId: string; show: boolean }) {
  const [data, setData] = useState<NearbyShops | null>(null);
  useEffect(() => {
    api.nearby(profileId, searchId).then(setData, () => setData(null));
  }, [profileId, searchId]);
  if (!show || !data?.enabled || !data.shops.length) return null;
  return (
    <section className="mt-10">
      <SectionTitle aside={data.zip_code ? `Near ${data.zip_code}` : undefined}>Shops near you</SectionTitle>
      <p className="text-sm text-muted mb-3">Worth a visit for this search. We can&apos;t see their stock, so call ahead.</p>
      <ul className="grid gap-3 sm:grid-cols-2">
        {data.shops.map((shop) => (
          <li key={shop.maps_url} className="border border-ink p-3 grid gap-1">
            <p className="text-display">{shop.name}</p>
            <p className="text-sm">{shop.why}</p>
            {/* Google's terms: each Maps source sits right after what it supports, named and linked. */}
            <a href={shop.maps_url} target="_blank" rel="noopener noreferrer" className="label underline" translate="no">
              {shop.name} on Google Maps ↗
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

// "Looked through 214 listings · left out 31 in the wrong size and 18 over $60 · average $38, $22 under your cap".
function Impact({ counts, results }: { counts: SearchCounts; results: Listing[] }) {
  const out = counts.left_out ?? {};
  const cap = counts.max_item_price;
  const reasons = [
    out.wrong_size && `${out.wrong_size} in the wrong size`,
    out.over_price && `${out.over_price} over ${cap ? money(cap) : "your cap"}`,
    out.sold && `${out.sold} already sold`,
  ].filter(Boolean) as string[];
  const average = results.length ? results.reduce((sum, item) => sum + item.price, 0) / results.length : 0;
  const parts = [
    `Looked through ${counts.retrieved.toLocaleString()} listings`,
    reasons.length > 0 && `left out ${reasons.length > 1 ? `${reasons.slice(0, -1).join(", ")} and ${reasons.at(-1)}` : reasons[0]}`,
    results.length > 0 && `average ${money(average)}${cap && cap > average ? `, ${money(cap - average)} under your cap` : ""}`,
  ].filter(Boolean);
  return <p className="label mb-3">{parts.join(" · ")}</p>;
}

// "Loading matches" → "3 matches so far" → "20 matches".
// "new" covers every store in the retailer bank (the mainstream actor); "secondhand" covers resale apps, small shops
// and independent labels' own stores (the indie actor).
type Kind = "all" | "secondhand" | "new";
const kindOf = (item: Listing): Kind => (item.source === "mainstream" ? "new" : "secondhand");

function MixFilter({ results, kind, onChange }: { results: Listing[]; kind: Kind; onChange: (kind: Kind) => void }) {
  if (!results.length) return null;
  const count = (k: Kind) => (k === "all" ? results.length : results.filter((item) => kindOf(item) === k).length);
  const options: [Kind, string][] = [["all", "All"], ["secondhand", "Secondhand & small shops"], ["new", "New from stores"]];
  return (
    <div className="flex flex-wrap gap-2 mb-3" role="group" aria-label="Show">
      {options.map(([k, label]) => (
        <button
          key={k}
          onClick={() => onChange(k)}
          aria-pressed={kind === k}
          className={`label border border-ink px-3 py-1 ${kind === k ? "bg-ink text-paper" : ""}`}
        >
          {label} {count(k)}
        </button>
      ))}
    </div>
  );
}

function matchCount(count: number, loading: boolean) {
  if (loading && count === 0) return "Loading matches";
  const noun = count === 1 ? "match" : "matches";
  return loading ? `${count} ${noun} so far` : `${count} ${noun}`;
}

// "Nordstrom · Department store", "Depop · Secondhand"; older single-marketplace results fall back to seller/source.
function storeLabel(listing: Listing) {
  if (!listing.retailer) return listing.seller ?? listing.source;
  return listing.tier ? `${listing.retailer} · ${TIER_LABELS[listing.tier]}` : listing.retailer;
}

function ListingDetail({
  listing,
  searchId,
  onPurchased,
}: {
  listing: Listing;
  searchId: string;
  onPurchased?: () => void;
}) {
  return (
    <div className="grid gap-4">
      <div>
        <p className="text-display">{listing.title}</p>
        <p className="text-display">{storeLabel(listing)}</p>
      </div>
      {!!listing.risks?.length && (
        <div role="alert" className="border-2 border-ink p-3 grid gap-1">
          <span className="label">⚠ Before you buy</span>
          {listing.risks.map((risk) => (
            <p key={risk} className="text-sm">{risk}</p>
          ))}
        </div>
      )}
      <div className="grid gap-1">
        <span className="label">Why this matches</span>
        <p className="text-sm">{listing.reason}</p>
        {[...new Set(listing.warnings)].map((w) => (
          <p key={w} className="text-xs text-muted">— {w}</p>
        ))}
      </div>
      <div className="rule-t pt-3">
        <Checkout searchId={searchId} listing={listing} onPurchased={onPurchased} />
      </div>
    </div>
  );
}
