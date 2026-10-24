# SpacetimeDB module: `niche`

Live, shared state for Niche. FastAPI still does the heavy work (Claude, Apify, Stripe). It writes results here through **service-only reducers**. Browsers subscribe to the public tables and call the moodboard reducers directly.

```
taste engine ──build_progress / profile_version──▶ ┐
sourcing pipeline ──search / listing (per source)──▶ ├─ SpacetimeDB ──subscriptions──▶ /upload, /taste, /shop
browsers ──move_piece / move_cursor──▶ ┘
```

## What uses it today

| Feature | Tables | Written by | Read by |
|---|---|---|---|
| Shared moodboard (drag together via **Share board**) | `board_piece` | `move_piece`, `reset_board` (any viewer holding the link) | `web/components/binder.tsx` |
| Live cursors with names | `board_cursor` | `move_cursor`, `leave_board`; cleared on disconnect | `binder.tsx` |
| Build progress ("Reading your images · 6 of 15") | `build_progress` | backend `set_build_progress` | `web/components/build-progress.tsx` |
| Refetch on any profile change (other tab, voice edit, rebuild) | `profile_version` | backend `set_profile_version` | `web/app/taste/page.tsx` |
| Search results streaming in per marketplace, then reranked | `search`, `listing` | backend `upsert_search`, `upsert_listings` | `web/app/shop/page.tsx` |

Boards are keyed `<profile id>:v<version>`, so a rebuilt profile starts with a fresh arrangement. The `service` table (private) holds the identities allowed to call service reducers. `init` seeds it with whoever publishes the module.

## Run locally

```sh
# 1. CLI (once): https://spacetimedb.com/install
curl -sSf https://install.spacetimedb.com | sh

# 2. Server on 3100 (Next.js uses 3000)
spacetime start --listen-addr 127.0.0.1:3100
spacetime server add niche-local --url http://127.0.0.1:3100   # once

# 3. Publish + regenerate client bindings
cd spacetime && npm install
npm run publish:local        # creates/updates the `niche` database
npm run generate             # writes web/lib/spacetime (commit the result)
```

The backend needs the publisher's token to call service reducers. Copy the `spacetimedb_token` value from `~/.config/spacetime/cli.toml` into `backend/.env` as `SPACETIME_TOKEN`, and set `SPACETIME_URL=http://127.0.0.1:3100`. With `SPACETIME_URL` blank the backend skips publishing, and the web app falls back to polling.

After changing the schema, republish and regenerate. Breaking changes need `spacetime publish niche --server niche-local --delete-data=always --yes` (this wipes live state only; profiles and images live in the backend).

## Gotchas

- The HTTP reducer API takes **snake_case** field names and encodes options as `{"some": v}` / `{"none": []}` (see `backend/sourcing/live.py`).
- Any viewer holding a board link can move its pieces. Profile edits and notes stay owner-only, through the REST API.
- `spacetime call` treats negative numbers as flags. Avoid them when testing from the CLI.
