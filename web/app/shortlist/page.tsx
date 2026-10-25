"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Checkout } from "@/components/checkout";
import { SectionTitle } from "@/components/chrome";
import { Drawer } from "@/components/drawer";
import { api } from "@/lib/api";
import { getProfileId } from "@/lib/session";
import { TIER_LABELS, type ShortlistItem, type ShortlistView } from "@/lib/types";

// Clothing item kinds, in the order they're listed (backend/taste/chat.py CATEGORY_WORDS).
const CATEGORIES: [string, string][] = [
  ["top", "Tops"], ["bottom", "Bottoms"], ["dress", "Dresses & skirts"], ["outerwear", "Outerwear"],
  ["shoes", "Shoes"], ["bra", "Bras"], ["accessory", "Accessories"], ["other", "Other"],
];
const categoryLabel = (c: string) => CATEGORIES.find(([k]) => k === c)?.[1] ?? "Other";
const kindOf = (item: ShortlistItem) => (CATEGORIES.some(([k]) => k === item.category) ? item.category : "other");
const categoryRank = (c: string) => {
  const i = CATEGORIES.findIndex(([k]) => k === c);
  return i < 0 ? CATEGORIES.length : i;
};

type Sort = "newest" | "oldest" | "price_low" | "price_high" | "item";
const SORTS: [Sort, string][] = [
  ["newest", "Newest first"], ["oldest", "Oldest first"], ["price_low", "Price: low to high"],
  ["price_high", "Price: high to low"], ["item", "Clothing item"],
];
const UNSORTED = "\u0000unsorted"; // the collection filter for items not in any collection

/** Saved results: sort them into collections or by clothing item, then check out from here. */
export default function ShortlistPage() {
  const [profileId, setProfileId] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const [view, setView] = useState<ShortlistView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [collection, setCollection] = useState<string | null>(null); // null: all
  const [category, setCategory] = useState<string | null>(null); // null: every clothing item
  const [sort, setSort] = useState<Sort>("newest");
  const [naming, setNaming] = useState(false);
  const [newName, setNewName] = useState("");
  const [open, setOpen] = useState<ShortlistItem | null>(null);

  useEffect(() => {
    const id = getProfileId();
    if (!id) return setMissing(true);
    setProfileId(id);
    api.shortlist(id).then(setView, (err) => setError((err as Error).message));
  }, []);

  async function change(task: () => Promise<ShortlistView>) {
    setError(null);
    try {
      setView(await task());
    } catch (err) {
      setError((err as Error).message);
    }
  }

  if (missing) {
    return (
      <p className="px-4 mt-10 text-display">
        Build your <Link href="/onboard" className="underline">taste profile</Link> first, then shortlist what you find.
      </p>
    );
  }
  if (!view || !profileId) return <p className="px-4 mt-10 label">{error ?? "Loading…"}</p>;
  const id = profileId;

  const inCollection = view.items.filter((x) =>
    collection === null ? true : collection === UNSORTED ? !x.collection : x.collection === collection,
  );
  const shown = inCollection
    .filter((x) => category === null || kindOf(x) === category)
    .sort((a, b) => {
      if (sort === "price_low") return a.listing.price - b.listing.price;
      if (sort === "price_high") return b.listing.price - a.listing.price;
      if (sort === "oldest") return a.created_at.localeCompare(b.created_at);
      if (sort === "item") return categoryRank(kindOf(a)) - categoryRank(kindOf(b)) || b.created_at.localeCompare(a.created_at);
      return b.created_at.localeCompare(a.created_at);
    });
  const presentCategories = CATEGORIES.filter(([k]) => inCollection.some((x) => kindOf(x) === k));
  const unsortedCount = view.items.filter((x) => !x.collection).length;

  async function addCollection(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    await change(() => api.addCollection(id, name));
    setNewName("");
    setNaming(false);
    setCollection(name);
  }

  const chip = (active: boolean) => `label border border-ink px-3 py-1 ${active ? "bg-ink text-paper" : ""}`;

  return (
    <div className="px-4 mt-6 grid gap-4">
      <SectionTitle aside={`${view.items.length} saved`}>Your shortlist</SectionTitle>
      {view.items.length > 0 && (
        <p className="label -mt-2">
          {view.items.filter((item) => item.listing.source === "secondhand").length} secondhand ·{" "}
          {view.items.filter((item) => item.listing.source === "indie" || item.listing.source === "web").length} from
          independent labels · {view.items.filter((item) => item.listing.source === "mainstream").length} new from big stores
        </p>
      )}
      {error && <p className="text-sm">{error}</p>}

      {view.items.length === 0 && view.collections.length === 0 ? (
        <p className="text-display">
          Nothing here yet. Tap <span className="label bg-ink text-paper px-2 py-0.5">+ Shortlist</span> on anything you
          like in <Link href="/shop" className="underline">Shop</Link>, then come back here to check out.
        </p>
      ) : (
        <>
          <div className="grid gap-2">
            <span className="label text-muted">Collections</span>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Collections">
              <button onClick={() => setCollection(null)} aria-pressed={collection === null} className={chip(collection === null)}>
                All {view.items.length}
              </button>
              {view.collections.length > 0 && (
                <button onClick={() => setCollection(UNSORTED)} aria-pressed={collection === UNSORTED} className={chip(collection === UNSORTED)}>
                  Unsorted {unsortedCount}
                </button>
              )}
              {view.collections.map((name) => (
                <span key={name} className={`${chip(collection === name)} flex items-center gap-2 !px-0`}>
                  <button onClick={() => setCollection(name)} aria-pressed={collection === name} className="pl-3">
                    {name} {view.items.filter((x) => x.collection === name).length}
                  </button>
                  <button
                    onClick={() => {
                      if (!window.confirm(`Delete the "${name}" collection? Its pieces stay on your shortlist.`)) return;
                      if (collection === name) setCollection(null);
                      change(() => api.removeCollection(id, name));
                    }}
                    aria-label={`Delete the ${name} collection`}
                    className="pr-2 opacity-60 hover:opacity-100"
                  >
                    ×
                  </button>
                </span>
              ))}
              {naming ? (
                <form onSubmit={addCollection} className="flex gap-1">
                  <input
                    autoFocus
                    className="input !py-1 text-sm w-40"
                    placeholder="e.g. Summer trip"
                    maxLength={40}
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onBlur={() => !newName.trim() && setNaming(false)}
                  />
                  <button className="label border border-ink px-3 py-1">Add</button>
                </form>
              ) : (
                <button onClick={() => setNaming(true)} className="label underline px-1">+ New collection</button>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-end justify-between gap-3">
            <div className="grid gap-2">
              <span className="label text-muted">Clothing item</span>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Clothing item">
                <button onClick={() => setCategory(null)} aria-pressed={category === null} className={chip(category === null)}>
                  Everything
                </button>
                {presentCategories.map(([k, label]) => (
                  <button key={k} onClick={() => setCategory(k)} aria-pressed={category === k} className={chip(category === k)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <label className="label flex items-center gap-2">
              Sort
              <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} className="border border-ink bg-paper px-2 py-1">
                {SORTS.map(([k, label]) => (
                  <option key={k} value={k}>{label}</option>
                ))}
              </select>
            </label>
          </div>

          {shown.length === 0 ? (
            <p className="text-sm text-muted">Nothing in this view yet.</p>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-2 gap-y-6">
              {shown.map((item, i) => (
                <div key={item.id} className="contents">
                  {sort === "item" && (i === 0 || kindOf(shown[i - 1]) !== kindOf(item)) && (
                    <p className="col-span-full text-display rule-b pb-1">{categoryLabel(kindOf(item))}</p>
                  )}
                  <SavedCard
                    item={item}
                    collections={view.collections}
                    onOpen={() => setOpen(item)}
                    onMove={(name) => change(() => api.moveShortlistItem(id, item.id, name))}
                    onRemove={() => change(() => api.removeShortlistItem(id, item.id))}
                  />
                </div>
              ))}
            </div>
          )}
        </>
      )}

      <Drawer open={!!open} onClose={() => setOpen(null)}>
        {open && (
          <div className="grid gap-4">
            <div>
              <p className="text-display">{open.listing.title}</p>
              <p className="text-display">{storeLabel(open)}</p>
            </div>
            {!!open.listing.risks?.length && (
              <div role="alert" className="border-2 border-ink p-3 grid gap-1">
                <span className="label">⚠ Before you buy</span>
                {open.listing.risks.map((risk) => (
                  <p key={risk} className="text-sm">{risk}</p>
                ))}
              </div>
            )}
            {open.listing.reason && (
              <div className="grid gap-1">
                <span className="label">Why it matched</span>
                <p className="text-sm">{open.listing.reason}</p>
              </div>
            )}
            {open.learning && (
              <div className="grid gap-1">
                <span className="label">What your taste profile learned</span>
                <p className="text-sm">{open.learning}</p>
              </div>
            )}
            <div className="rule-t pt-3">
              <Checkout searchId={open.search_id} listing={open.listing} />
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}

function storeLabel(item: ShortlistItem) {
  const l = item.listing;
  if (!l.retailer) return l.seller ?? l.source;
  return l.tier ? `${l.retailer} · ${TIER_LABELS[l.tier]}` : l.retailer;
}

function SavedCard({
  item,
  collections,
  onOpen,
  onMove,
  onRemove,
}: {
  item: ShortlistItem;
  collections: string[];
  onOpen: () => void;
  onMove: (collection: string | null) => void;
  onRemove: () => void;
}) {
  const l = item.listing;
  return (
    <figure className="relative grid content-start gap-1">
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${l.title} from your shortlist`}
        className="absolute right-1 top-1 z-10 bg-paper border border-ink size-7 leading-none text-lg"
      >
        ×
      </button>
      <button onClick={onOpen} className="text-left">
        <div className="bg-plinth aspect-[3/4] flex items-center justify-center overflow-hidden">
          {l.image_urls[0] ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={l.image_urls[0]} alt="" className="h-full w-full object-contain" />
          ) : (
            <span className="label text-muted">{l.is_fixture ? "Demo item" : "No photo"}</span>
          )}
        </div>
        <div className="flex justify-between mt-1 gap-2">
          <span className="label pt-0.5">{categoryLabel(kindOf(item))}</span>
          <span className="label pt-0.5 text-right">{storeLabel(item)}</span>
        </div>
        <p className="text-sm">{l.title}</p>
        <p className="text-sm">{l.price.toFixed(2)} {l.currency}</p>
      </button>
      <select
        aria-label="Collection"
        value={item.collection ?? ""}
        onChange={(e) => {
          const value = e.target.value;
          if (value === "\u0000new") {
            const name = window.prompt("Name the new collection")?.trim();
            if (name) onMove(name);
            return;
          }
          onMove(value || null);
        }}
        className="label border border-ink bg-paper px-2 py-1"
      >
        <option value="">No collection</option>
        {collections.map((name) => (
          <option key={name} value={name}>{name}</option>
        ))}
        <option value={"\u0000new"}>+ New collection…</option>
      </select>
      <button onClick={onOpen} className="label bg-ink text-paper px-3 py-2 hover:opacity-85">
        Check out
      </button>
    </figure>
  );
}
