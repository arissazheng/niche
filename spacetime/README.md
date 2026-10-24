# SpacetimeDB module (owner: Zaara)

Not initialized yet. The `spacetime` CLI isn't installed on the scaffolding machine. Install it, then run `spacetime init` in this directory using the module language you prefer. Check every API name below against the current SpacetimeDB docs: this file is a contract, not code.

## Why it is the core backend

SpacetimeDB holds the live, shared state that several agents write and the UI subscribes to:

```
voice agent ──transcripts/edits──▶ ┐
taste engine ──profile versions──▶ ├─ SpacetimeDB ──subscriptions──▶ moodboard / chat UI
sourcing agents ──listings as each Apify source finishes──▶ ┘
```

The FastAPI backend still does the heavy work (Claude, Apify, Stripe). Each time it produces a result, it calls a reducer, so the UI updates without polling. `web/app/shop/page.tsx` has a `TODO(spacetime)` at the polling loop this replaces.

## Proposed tables

| Table | Key fields | Written by |
|---|---|---|
| `user` | identity, profile_id, name, email, sizes, budget, usual_shops | onboarding (voice or form) |
| `taste_profile` | profile_id, version, summary, prompt, colors, silhouettes, patterns, avoid, mode | backend after build/edit |
| `moodboard_item` | id, profile_id, image_url, cluster, note, palette | backend after upload/build |
| `voice_turn` | session_id, role (user/agent), text, at | voice agent |
| `profile_edit` | profile_id, source (voice/text/manual), instruction, at | backend /edit |
| `search` | search_id, profile_id, query, status, ranking_method | backend sourcing |
| `listing` | search_id, listing_id, source, title, price, image_url, reason, score | backend as sources finish |
| `purchase` | listing_id, payment_intent_id, status, ledger_ref | backend checkout |

## Proposed reducers

`upsert_profile`, `add_moodboard_item`, `append_voice_turn`, `record_edit`, `upsert_search`, `add_listing`, `record_purchase`.

## Integration points to build

- Backend: a small `live.py` publisher that calls reducers. It is called from `taste/engine.py` (`apply`), `sourcing/pipeline.py` (after each source and after ranking) and `checkout/api.py` (`confirm`).
- Web: generate client bindings and subscribe by `profile_id` / `search_id` on `/taste` and `/shop`.
