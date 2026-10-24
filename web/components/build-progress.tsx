"use client";

import { useTable } from "spacetimedb/react";
import { tables } from "@/lib/spacetime";

/** Live build status from SpacetimeDB ("Reading your images · 6 of 15"); falls back to a plain label. */
export function BuildProgress({ profileId, fallback = "Curating your profile…" }: { profileId: string; fallback?: string }) {
  const [rows] = useTable(tables.buildProgress.where((r) => r.profileId.eq(profileId)));
  const row = rows[0];
  if (!row || row.stage === "done" || row.stage === "failed") return <>{fallback}</>;
  if (row.stage === "extracting" && row.total > 0) return <>{`${row.message} · ${row.done} of ${row.total}`}</>;
  return <>{row.message || fallback}</>;
}
