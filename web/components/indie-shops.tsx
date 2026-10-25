"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { BrandSuggestion, IndieShop, ProfileView } from "@/lib/types";
import type { Change } from "@/components/profile-panel";

/** The shopper's own independent labels: every search reads these stores directly, so they show up new, not only
 *  secondhand. A brand name or website goes in; the backend finds its Shopify store (taste/shops.py). */
export function IndieShops({ view, onChange }: { view: ProfileView; onChange: Change }) {
  const { profile } = view;
  const shops = profile.indie_shops ?? [];
  const [text, setText] = useState("");
  const [working, setWorking] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<BrandSuggestion[] | null>(null);
  const built = profile.version > 0;
  const shopNames = new Set(shops.map((shop) => shop.name.toLowerCase()));
  const favorites = (profile.onboarding.favorite_brands ?? []).filter((name) => !shopNames.has(name.toLowerCase()));
  const shopKey = shops.map((shop) => shop.domain).join(",");
  useEffect(() => {
    if (!built) return;
    let live = true;
    setSuggestions(null);
    api.brandSuggestions(profile.id).then((r) => live && setSuggestions(r.suggestions), () => live && setSuggestions([]));
    return () => {
      live = false;
    };
  }, [profile.id, profile.version, built, shopKey]);

  async function change(task: () => Promise<ProfileView>, pending: string, done: string) {
    setWorking(pending);
    setStatus(null);
    const error = await onChange(task);
    setWorking(null);
    setStatus(error ?? done);
    return !error;
  }

  return (
    <section className="grid gap-3">
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-display">Brands &amp; stores you like</h2>
        {shops.length + favorites.length > 0 && <span className="label">{shops.length + favorites.length}</span>}
      </div>
      <p className="text-sm">
        Any brand or store, big or small. Labels with their own online shop get searched directly every time, so you
        see their new pieces, not only resale. The rest are favorites that Niche looks for and ranks a little higher.
      </p>
      {shops.length > 0 && (
        <ul className="grid gap-1 text-sm">
          {shops.map((shop) => (
            <li key={shop.domain} className="flex justify-between gap-2 rule-b py-1">
              <span>
                {shop.name} <span className="text-muted">· {shop.domain}</span> <Badge shop={shop} />
              </span>
              <button
                disabled={!!working}
                onClick={() => change(() => api.removeShop(profile.id, shop.domain), "Removing…", `Removed ${shop.name}.`)}
                className="label underline disabled:no-underline disabled:text-muted"
                aria-label={`Remove ${shop.name}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      {favorites.length > 0 && (
        <ul className="grid gap-1 text-sm">
          {favorites.map((name) => (
            <li key={name} className="flex justify-between gap-2 rule-b py-1">
              <span>
                {name} <span className="text-muted">· favorite</span>
              </span>
              <button
                disabled={!!working}
                onClick={() =>
                  change(
                    () =>
                      api.updateOnboarding(profile.id, {
                        ...profile.onboarding,
                        favorite_brands: (profile.onboarding.favorite_brands ?? []).filter((x) => x !== name),
                      }),
                    "Removing…",
                    `Removed ${name}.`,
                  )
                }
                className="label underline disabled:no-underline disabled:text-muted"
                aria-label={`Remove ${name}`}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="grid gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          const shop = text.trim();
          if (shop.length < 2 || working) return;
          setWorking(`Looking for ${shop}…`);
          setStatus(null);
          let message = "";
          const error = await onChange(async () => {
            const next = await api.addShop(profile.id, shop);
            // Searched directly when its own shop was found; otherwise kept as a favorite brand.
            const direct = (next.profile.indie_shops ?? []).length > shops.length;
            message = direct ? `Added ${shop}: Niche searches its shop directly.` : `Saved ${shop} as a favorite.`;
            return next;
          });
          setWorking(null);
          setStatus(error ?? message);
          if (!error) setText("");
        }}
      >
        <input
          className="input"
          placeholder="Brand, store or website, e.g. Batul The Collection, Aritzia"
          value={text}
          disabled={!!working}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="flex justify-between gap-2">
          <p className={`text-xs min-h-4 ${working ? "animate-pulse" : ""}`} role="status" aria-live="polite">
            {working ?? status}
          </p>
          <button disabled={!!working || text.trim().length < 2} className="label underline disabled:no-underline disabled:text-muted">
            Add
          </button>
        </div>
      </form>
      {built && (
        <div className="grid gap-2 mt-2">
          <span className="label">Brands you might like</span>
          {suggestions === null ? (
            <p className="text-xs animate-pulse">Finding independent labels close to your taste and checking them…</p>
          ) : suggestions.length === 0 ? (
            <p className="text-xs">No verified labels to suggest yet. Add a few favorites above and check back.</p>
          ) : (
            <ul className="grid gap-2 text-sm">
              {suggestions.map(({ shop, reason }) => (
                <li key={shop.domain} className="flex justify-between gap-3 rule-b pb-2">
                  <span>
                    <a href={`https://${shop.domain}`} target="_blank" rel="noreferrer" className="underline">
                      {shop.name}
                    </a>{" "}
                    <Badge shop={shop} />
                    <span className="block text-xs">{reason}</span>
                  </span>
                  <button
                    disabled={!!working}
                    onClick={() => change(() => api.addShop(profile.id, shop.domain), `Adding ${shop.name}…`, `Added ${shop.name}.`)}
                    className="label underline self-start disabled:no-underline disabled:text-muted"
                  >
                    Add
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

const CHECK_LABELS: Record<string, string> = {
  real_store: "sells in-stock pieces from its own site",
  independent: "not a marketplace or chain",
  own_label: "its own label, not a reseller",
  small: "a small catalog",
  established: "selling for over six months",
};

/** "Verified independent" when the shop passed every check; the checks themselves are in the tooltip. */
function Badge({ shop }: { shop: IndieShop }) {
  if (shop.verified !== true) return null;
  const passed = Object.entries(shop.checks ?? {}).filter(([, ok]) => ok).map(([k]) => CHECK_LABELS[k] ?? k);
  return (
    <span className="label border border-ink px-1 ml-1" title={`Checked: ${passed.join(", ")}`}>
      Verified independent
    </span>
  );
}
