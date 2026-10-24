"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useSpacetimeDB, useTable } from "spacetimedb/react";
import { Checkout } from "@/components/checkout";
import { SectionTitle } from "@/components/chrome";
import { Drawer } from "@/components/drawer";
import { VoiceButton } from "@/components/voice";
import { api } from "@/lib/api";
import { getProfileId } from "@/lib/session";
import { tables } from "@/lib/spacetime";
import { TIER_LABELS, type Listing, type SearchJob } from "@/lib/types";

const DONE = new Set(["completed", "partial", "failed", "interrupted"]);

export default function ShopPage() {
  const [profileId, setProfileIdState] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [job, setJob] = useState<SearchJob | null>(null);
  const [selected, setSelected] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searchId, setSearchId] = useState<string | null>(null);

  useEffect(() => setProfileIdState(getProfileId()), []);

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

  async function search(text: string) {
    if (!profileId || !text.trim()) return;
    setError(null);
    setJob(null);
    try {
      const { search_id, status_url } = await api.search(profileId, text);
      setSearchId(search_id);
      // The live subscription drives the page; polling just picks up the final record (and covers a
      // dropped SpacetimeDB connection, when it polls faster).
      for (;;) {
        const next = await api.getSearch(status_url);
        setJob(next);
        if (DONE.has(next.status)) break;
        await new Promise((r) => setTimeout(r, isActive ? 4000 : 1500));
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (!profileId) {
    return (
      <p className="px-4 mt-10 text-display">
        Build your <Link href="/onboard" className="underline">taste profile</Link> first.
      </p>
    );
  }

  const finished = !!job && DONE.has(job.status);
  const results = finished ? job.results ?? [] : liveListings.length ? liveListings : job?.results ?? [];
  const status = finished ? job.status : liveSearch[0]?.status ?? job?.status;
  const ranked = finished || liveRows.some((r) => r.rank !== undefined);
  return (
    <div className="px-4 mt-6">
      <form
        className="rule-t rule-b flex items-center gap-3 py-2"
        onSubmit={(e) => {
          e.preventDefault();
          search(query);
        }}
      >
        <input
          className="flex-1 text-display bg-transparent outline-none placeholder:text-muted"
          placeholder="Find me wide-leg trousers for fall"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <VoiceButton context="shop" label="Ask" onTranscript={(t) => (setQuery(t), search(t))} />
        <button className="label underline">Search</button>
      </form>

      {error && <p className="text-sm mt-3">{error}</p>}
      {status && !DONE.has(status) && (
        <p className="label mt-3 animate-pulse">
          {results.length
            ? `${results.length} found so far · ${ranked ? "ranking" : "comparing them to your taste"}…`
            : "Searching stores and secondhand sellers…"}
        </p>
      )}
      {job?.warnings?.map((w) => (
        <p key={w} className="label mt-2 text-muted">{w}</p>
      ))}

      {results.length > 0 && (
        <section className="mt-8">
          <SectionTitle aside={job?.ranking_method}>{results.length} matches</SectionTitle>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {results.map((item, i) => (
              <button key={item.id} onClick={() => setSelected(item)} className="text-left">
                <div className="bg-plinth aspect-[3/4] flex items-center justify-center overflow-hidden">
                  {item.image_urls[0] ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={item.image_urls[0]} alt="" className="max-h-full max-w-full object-contain" />
                  ) : (
                    <span className="label text-muted">{item.is_fixture ? "Demo item" : "No photo"}</span>
                  )}
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-display">{i + 1}</span>
                  <span className="label pt-1">{storeLabel(item)}</span>
                </div>
                <p className="text-sm">{item.title}</p>
                <p className="text-sm">{item.price.toFixed(2)} {item.currency}</p>
              </button>
            ))}
          </div>
        </section>
      )}

      <Drawer open={!!selected} onClose={() => setSelected(null)}>
        {selected && job && <ListingDetail listing={selected} searchId={job.search_id} />}
      </Drawer>
    </div>
  );
}

// "Nordstrom · Department store", "Depop · Secondhand"; older single-marketplace results fall back to seller/source.
function storeLabel(listing: Listing) {
  if (!listing.retailer) return listing.seller ?? listing.source;
  return listing.tier ? `${listing.retailer} · ${TIER_LABELS[listing.tier]}` : listing.retailer;
}

function ListingDetail({ listing, searchId }: { listing: Listing; searchId: string }) {
  return (
    <div className="grid gap-4">
      <div>
        <p className="text-display">{listing.title}</p>
        <p className="text-display">{storeLabel(listing)}</p>
        <p className="text-display">{listing.price.toFixed(2)} {listing.currency}</p>
      </div>
      <div className="grid gap-1">
        <span className="label">Why this matches</span>
        <p className="text-sm">{listing.reason}</p>
        {listing.warnings.map((w) => (
          <p key={w} className="text-xs text-muted">— {w}</p>
        ))}
        {listing.is_fixture ? (
          <p className="label mt-1">Synthetic demo item</p>
        ) : (
          <a href={listing.url} target="_blank" rel="noreferrer" className="label underline mt-1">View on {listing.retailer ?? listing.source} ↗</a>
        )}
      </div>
      <div className="rule-t pt-3">
        <Checkout searchId={searchId} listing={listing} />
      </div>
    </div>
  );
}
