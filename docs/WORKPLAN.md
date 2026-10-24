# Two-engineer workplan

The original plan had three owners. Person 3 (sourcing + checkout) left, but their sourcing service is already built and lives in `backend/sourcing/`. The split below balances that against what is still unbuilt.

| | **Zaara — real-time, voice & conversation** | **Arissa — taste, sourcing & checkout** |
|---|---|---|
| Owns | Voice agent, SpacetimeDB (core live backend), chat wrapper, onboarding flow | Taste engine, moodboard and profile UI, Apify sourcing (live validation), Nessie budget + "Mark as bought" |
| Code | `web/components/voice.tsx`, `web/app/onboard/`, `web/app/shop/` (search bar + live results), `spacetime/`, a backend voice-token route | `backend/taste/`, `backend/sourcing/`, `backend/checkout/`, `web/app/taste/`, `web/components/checkout.tsx` |
| Already scaffolded | Voice seam (`VoiceButton` + `onTranscript`), onboarding form, shop page with polling | Fixture + Claude taste pipeline, endpoints and tests; sourcing service (17 tests); Nessie budget-aware agent |

## Features → owner → tools / APIs to use

| Feature | Owner | Tools / APIs | Prize track it scores for |
|---|---|---|---|
| Profile setup questions (name, age, email, sizes, budget slider, usual shops) | Zaara | **Cartesia** and/or **Moss** voice agent; form fallback already built; answers saved via `PUT /v1/taste/profiles/{id}/onboarding` and the **SpacetimeDB** `user` table | Cartesia, Moss, SpacetimeDB |
| Voice bake-off (latency, voice quality, ease of use) → cut the weaker one by **Oct 24 midday** | Zaara | **Cartesia API**, **Moss API**; keys stay server-side, browser gets a short-lived token | Cartesia, Moss |
| Image upload (outfits + individual pieces) | Arissa | FastAPI multipart, **Pillow** (measured color palette) | Anthropic |
| Click an image to add details ("I like the color, not the frills") | Arissa (UI + engine), Zaara (voice input via `VoiceButton`) | `PUT /v1/taste/images/{id}/note`; voice transcript → note | Anthropic, Cartesia/Moss |
| Object extraction (garments, colors, silhouettes, patterns, materials, visible designers) | Arissa | **Claude API** (`claude-opus-5-5`, vision + structured outputs) | Anthropic |
| Multimodal clustering → taste profile + editable prompt | Arissa | **Claude API** (all images + extractions + notes in one synthesis call) | Anthropic |
| Edit taste profile by text or voice ("less minimal, more vintage") | Arissa (`POST /edit` engine), Zaara (voice → `api.edit(id, text, "voice")`) | **Claude API**, **Cartesia/Moss** | Anthropic, Cartesia/Moss |
| System prompt visible in backend logs for debugging | Arissa | Python `logging` + `events` table (already wired for every Claude stage) | Anthropic ("know where it could go wrong") |
| Moodboard + taste-profile view | Arissa | Next.js; live updates via a **SpacetimeDB** subscription (Zaara exposes the hook) | Visa (UX), SpacetimeDB |
| Sourcing: small-business and secondhand marketplaces | Arissa | **Apify** actors: Etsy, Depop/Poshmark, Grailed; Claude query planner + multimodal ranker | **Apify**, Visa (commerce impact) |
| Chat wrapper: text/voice search, results stream into the moodboard | Zaara | **SpacetimeDB** (listings stream in as each Apify source finishes, replacing polling), **Cartesia/Moss** voice | SpacetimeDB, Cartesia/Moss, Visa |
| Buying (on the store's site) + "Mark as bought" | Arissa | Purchases complete on the seller's own site; marking an item bought records it to **Nessie** so the budget-aware agent stays accurate. Stripe was dropped: Niche doesn't sell items (optional per team) | Visa, Capital One |
| "Agentic finance" ledger | Arissa | **Capital One Nessie** mock bank: each purchase is mirrored to a mock account | Capital One |
| Design | Both | **Figma** (say in the demo that the Figma connector in Claude was used) | Figma |
| Post-MVP: saved taste profiles | Zaara | **SpacetimeDB** `taste_profile` rows per user | SpacetimeDB |
| Post-MVP: TikTok / Instagram / Pinterest imports | Arissa | **Apify** social scrapers → same image pipeline ("Apify powers everything") | Apify |

## Handoff contracts (keep these stable)

1. **Voice → app.** `VoiceButton({ context, onTranscript })` in `web/components/voice.tsx`. Pages only consume final transcripts, so swapping Cartesia for Moss touches nothing else.
2. **Voice/text edits → taste engine.** `POST /v1/taste/profiles/{id}/edit` with `{ instruction, source: "voice" | "text" }`.
3. **Taste → sourcing.** `POST /v1/taste/profiles/{id}/searches` with `{ query }`. It converts the profile into the sourcing `SearchRequest` and queues it.
4. **Backend → live UI.** The SpacetimeDB tables and reducers in `spacetime/README.md`. The backend writes there; the web subscribes.
5. **Results → purchase record.** `POST /v1/checkout/mark-bought` with `{ search_id, listing_id }`. The server looks up the price; the client never sends it.

## How judges score this (from the ideas doc)

- **SpacetimeDB** must be the core real-time backend, not an add-on. Here it is the live sync between the voice agent, the taste engine, the sourcing agents and the moodboard.
- **Anthropic:** name a specific community, show a real problem and a working product, and use Claude thoughtfully. Be able to say where it could fail: misread colors (we measure the palette from pixels), guessed brands (forbidden unless visible), invented results (ids are validated). The fallback model is enabled.
- **Visa:** 15% of the score is trust and responsibility. Covered by a visible, editable profile, a "why this matches" on every result, no sponsored boosts, and prices taken from the server.
- **Apify:** frame it as powering every data source.

## Open questions

