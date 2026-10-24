"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { PriceCheck } from "@/lib/types";

const VERDICT = { deal: "Good deal", fair: "Fair price", high: "Above typical" } as const;

/** "Typical $35–$60 across 18 similar listings · Good deal", from listing history in Snowflake. Hidden when unknown. */
export function MarketCheck({ searchId, listingId }: { searchId: string; listingId: string }) {
  const [check, setCheck] = useState<PriceCheck | null | "loading">("loading");
  useEffect(() => {
    let live = true;
    setCheck("loading");
    api.priceCheck(searchId, listingId).then(
      (out) => live && setCheck(out),
      () => live && setCheck(null),
    );
    return () => {
      live = false;
    };
  }, [searchId, listingId]);

  if (check === "loading") return <p className="label text-muted animate-pulse">Checking similar listings…</p>;
  if (!check || check.verdict === "unknown" || check.low === null || check.high === null) return null;
  return (
    <div className="grid gap-1">
      <span className="label">Market check</span>
      <p className="text-sm">
        Typical ${Math.round(check.low)}–${Math.round(check.high)} across {check.n} similar listings ·{" "}
        <span className="font-medium">{VERDICT[check.verdict]}</span>
      </p>
      {check.sentence && <p className="text-sm text-muted">{check.sentence}</p>}
      <p className="label text-muted">via Snowflake Cortex</p>
    </div>
  );
}
