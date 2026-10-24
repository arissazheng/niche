"use client";

import { useState } from "react";
import { SectionTitle } from "@/components/chrome";
import { api } from "@/lib/api";
import type { ProfileView } from "@/lib/types";
import type { Change } from "@/components/profile-panel";

/** The shopper's own independent labels: every search reads these stores directly, so they show up new, not only
 *  secondhand. A brand name or website goes in; the backend finds its Shopify store (taste/shops.py). */
export function IndieShops({ view, onChange }: { view: ProfileView; onChange: Change }) {
  const { profile } = view;
  const shops = profile.indie_shops ?? [];
  const [text, setText] = useState("");
  const [working, setWorking] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

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
      <SectionTitle aside={shops.length ? `${shops.length}` : undefined}>Your independent shops</SectionTitle>
      <p className="text-sm">
        Small labels you love. Niche searches their own stores on every search, so you get their new pieces and not
        only resale. Paste a website if the name isn&apos;t found. Brands you named when you signed up are looked up
        when you build your profile.
      </p>
      {shops.length > 0 && (
        <ul className="grid gap-1 text-sm">
          {shops.map((shop) => (
            <li key={shop.domain} className="flex justify-between gap-2 rule-b py-1">
              <span>
                {shop.name} <span className="text-muted">· {shop.domain}</span>
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
      <form
        className="grid gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          const shop = text.trim();
          if (shop.length < 2 || working) return;
          if (await change(() => api.addShop(profile.id, shop), `Looking for ${shop}'s shop…`, `Added ${shop}.`)) setText("");
        }}
      >
        <input
          className="input"
          placeholder="Brand name or website, e.g. Batul The Collection"
          value={text}
          disabled={!!working}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="flex justify-between gap-2">
          <p className={`text-xs min-h-4 ${working ? "animate-pulse" : ""}`} role="status" aria-live="polite">
            {working ?? status}
          </p>
          <button disabled={!!working || text.trim().length < 2} className="label underline disabled:no-underline disabled:text-muted">
            Add shop
          </button>
        </div>
      </form>
    </section>
  );
}
