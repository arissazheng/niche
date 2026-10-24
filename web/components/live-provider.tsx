"use client";

import { useMemo } from "react";
import { SpacetimeDBProvider } from "spacetimedb/react";
import { DbConnection } from "@/lib/spacetime";

// One SpacetimeDB connection for the whole app: live moodboard, build progress, streaming search results.
export const SPACETIMEDB_HOST = process.env.NEXT_PUBLIC_SPACETIMEDB_HOST ?? "ws://127.0.0.1:3100";
export const SPACETIMEDB_DB = process.env.NEXT_PUBLIC_SPACETIMEDB_DB ?? "niche";
const TOKEN_KEY = `${SPACETIMEDB_HOST}/${SPACETIMEDB_DB}/auth_token`;

function savedToken() {
  if (typeof window === "undefined") return undefined; // the provider only connects in the browser
  try {
    return localStorage.getItem(TOKEN_KEY) ?? undefined;
  } catch {
    return undefined;
  }
}

export function LiveProvider({ children }: { children: React.ReactNode }) {
  const builder = useMemo(
    () =>
      DbConnection.builder()
        .withUri(SPACETIMEDB_HOST)
        .withDatabaseName(SPACETIMEDB_DB)
        .withToken(savedToken())
        .withAutomaticReconnect()
        .onConnect((_conn, _identity, token) => {
          try {
            localStorage.setItem(TOKEN_KEY, token);
          } catch {
            // Without storage each visit is a new anonymous identity; everything still works.
          }
        }),
    [],
  );
  return <SpacetimeDBProvider connectionBuilder={builder}>{children}</SpacetimeDBProvider>;
}
