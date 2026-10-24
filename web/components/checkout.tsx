"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Listing } from "@/lib/types";

/**
 * Niche doesn't sell items: the shopper buys on the store's own site, then marks the item as bought so their
 * budget (and the shopping agent's view of it) stays accurate.
 */
export function Checkout({
  searchId,
  listing,
  onPurchased,
}: {
  searchId: string;
  listing: Listing;
  onPurchased?: () => void;
}) {
  const [state, setState] = useState<"idle" | "saving" | "done">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const store = listing.retailer ?? listing.seller ?? listing.source;

  async function markBought() {
    setState("saving");
    setMessage(null);
    try {
      const result = await api.markBought(searchId, listing.id);
      if (result.recorded && result.ledger) {
        setMessage(`Added $${result.ledger.amount} to this month's clothing spend.`);
      } else if (result.reason === "already_marked") {
        setMessage("Already marked as bought.");
      } else {
        setMessage("Noted. Link a bank account to track it against your budget.");
      }
      setState("done");
      onPurchased?.();
    } catch (err) {
      setMessage((err as Error).message);
      setState("idle");
    }
  }

  return (
    <div className="grid gap-2">
      <p className="text-display">
        {listing.price.toFixed(2)} {listing.currency}
      </p>
      {listing.is_fixture ? (
        <p className="label text-muted">Synthetic demo item · not for sale</p>
      ) : (
        <a
          href={listing.url}
          target="_blank"
          rel="noreferrer"
          className="rule-t rule-b text-display py-2 text-center"
        >
          Buy on {store} ↗
        </a>
      )}
      <button
        onClick={markBought}
        disabled={state !== "idle"}
        className="label underline justify-self-start disabled:no-underline disabled:text-muted"
      >
        {state === "saving" ? "Saving…" : state === "done" ? "Marked as bought" : "Bought it? Mark as bought"}
      </button>
      {message && <p className="text-sm">{message}</p>}
    </div>
  );
}
