# Niche

**Shopping agents that know your taste, not who paid for placement.**

Ask an AI to help you shop for clothes today and you get generic suggestions from the same big brands, often shaped
by sponsorships between AI companies and retailers. Niche starts from *your* style instead. You add photos of outfits
and pieces you love (uploads, Pinterest, Instagram, TikTok, or a few words). Claude builds an editable, multimodal
taste profile and a moodboard from them. Then a shopping agent searches independent labels, secondhand marketplaces,
local shops and major retailers side by side and ranks every piece by fit to your taste, size and budget, with the
reason why. There are no sponsored placements, and small sellers are as easy to find as brands that keyword-stuff
their listings.

Built at Cal Hacks 13.0 by Arissa Zheng and Zaara.

---

## What it does

| Step | What happens |
|---|---|
| **1. Tell us** (`/onboard`) | An open-encyclopedia profile: name, sizes (women's/men's charts, US/UK/EU/Asia, measurements → sizes), everyday budget, where you shop, optional ZIP for nearby shops, and consent before any photo goes to Claude. Fill it in by hand or just talk to the Niche assistant. |
| **2. Show us** (`/upload`) | The lookbook: drop or paste photos from anywhere, import public Pinterest boards/pins, Instagram posts/profiles and TikToks, or describe a look in words. Tap a photo to say what you like about it ("the colour, not the frills"). |
| **3. Your taste** (`/taste`) | Claude reads every photo, clusters your style and writes a taste profile. It's shown as a ring-bound moodboard with style clusters, notes and colours measured from the clothes (background and skin excluded). Edit it by typing or by voice. Share it to Instagram, TikTok or X as an image, or share a link with a friend. |
| **4. Shop for you** (`/shop`) | Chat with the shopping agent ("find me an asymmetrical buttoned top", "like Lewkin but Korean y2k"). It searches immediately and asks first only when a search is its own idea. Results stream in, ranked by Claude with a reason and caveats for each. Compare pieces in chat ("#2 or #5?"), keep a **Shortlist**, and open any listing for a **Market check** and **Before you buy** warnings. |
| **Shop for a friend** (`/friend/<token>`, `/gift/<token>`) | Share your taste link; a friend sees a view-only moodboard and can **find something for you**: gift searches use *your* taste and sizes with *their* budget. |

### Trust and responsibility, built in
- **No sponsored results.** Promoted listings are dropped before ranking; Shein, its house labels and Fashion Nova are never shown.
- **Explainable ranking.** Every result says why it matches; [`/how-it-works`](web/app/how-it-works/page.tsx) explains the whole pipeline in plain language.
- **Before you buy:** warnings for prices far below similar listings, requests to pay off-platform (Venmo, "DM to buy"), sellers with no or poor reviews, and the same item posted by many look-alike accounts.
- **Privacy:**
  - Consent before photos go to Claude, and your name, email, age and ZIP are never sent to Claude.
  - Photo links are signed and expire.
  - **Delete my data** wipes everything, including the live SpacetimeDB copy.
  - Friend links are revocable tokens that never expose your profile.
- **Your budget, your call.** With *Keep to budget* on, searches stay inside what's left of your monthly clothing budget (from your linked Nessie demo bank); off by default.

---

## Architecture

```
            ┌──────────────── web (Next.js 15, React, Tailwind v4) ─────────────────┐
            │ /onboard  /upload  /taste  /shop  /shortlist  /friend  /gift  /how-it-works │
            │ Niche assistant (voice + text, every page)   live moodboard / results     │
            └───────────────┬──────────────────────────────────────┬────────────────┘
                     REST (FastAPI)                         WebSocket subscriptions
                            │                                      │
┌───────────────────────── backend (Python, FastAPI) ─────────┐   ┌─▼──────────────────────┐
│ taste/    profile, photos, Claude extraction → clusters,    │──▶│ SpacetimeDB module     │
│           chat agent, shortlist, sharing, nearby (Gemini),  │   │ board pieces, cursors, │
│           earlier finds + labels (Moss), imports (Bright    │   │ build progress, search │
│           Data), share images, signed photo links           │   │ + streaming listings   │
│ sourcing/ query planning (Claude) → Apify actors + Bright   │   └────────────────────────┘
│           Data web shops → hard filters → photo ranking     │
│           (Claude) → mix, dedupe, scam checks               │──▶ Apify: niche-mainstream,
│ market/   Snowflake SQL API + Cortex: price history check   │    niche-secondhand, niche-indie,
│ finance/  Capital One Nessie: budget snapshot, purchases    │    independent-labels (ours)
│ voice/    Cartesia speech-to-text and text-to-speech        │──▶ Claude, Gemini, Snowflake,
│ checkout/ "mark as bought" → Nessie ledger                  │    Nessie, Cartesia, Moss, Bright Data
└─────────────────────────────────────────────────────────────┘
```

**Search pipeline** (`backend/sourcing/pipeline.py`):
1. **Plan.** Claude turns the brief and taste profile into search phrases, keeping brands and regional styles you named.
2. **Fetch in parallel:**
   - major retailers via Google Shopping
   - Depop, Poshmark, Vinted, Etsy and Grailed
   - our curated independent Shopify labels plus the shops you saved
   - independent web shops found through Bright Data
3. **Hard filters:** your size per category, price cap, availability, excluded brands.
4. **Rank.** Claude compares each photo against your taste, and the request's defining features come first. Pre-loaded listings are tagged with visible features from their photos, so only proven matches show before ranking.
5. **Finish the page:** a mix floor for new versus secondhand, a per-seller cap, collapsing duplicate listings, and scam checks.

**Storage:** SQLite for the API's record, SpacetimeDB for live shared state, Snowflake for public listing history, and Moss for semantic recall.

---

## Prize tracks and how Niche uses each

| Track | How Niche integrates it | Where |
|---|---|---|
| **Anthropic (Claude)** | Claude is the core of the product. It reads every lookbook photo, clusters taste and writes the profile, plans searches, ranks listings by looking at their photos against your taste (structured outputs), and runs the shopping chat (propose/search, compare, gift mode), the assistant and the Snowflake verdicts via Cortex. Server-side refusal fallback; consent and data minimisation before anything is sent. | `backend/taste/engine.py`, `backend/taste/chat.py`, `backend/sourcing/claude.py` |
| **Visa: Reimagining Shopping** | Covers discovery (conversational, multimodal search), decision-making (compare in chat, market check), personalization (taste profile), checkout/payments (budget-aware agent, shortlist → store → mark bought), and trust (explanations, scam warnings, consent, delete). Each search shows its impact: how many listings were checked and how many were left out for size or price. | `/shop`, `/how-it-works`, `backend/sourcing/risk.py` |
| **Capital One Nessie** | A linked demo bank account gives the agent your balance, this month's clothing spend and upcoming bills. With *Keep to budget* on, it caps searches at what's left and mentions tight weeks. Marking an item as bought records a purchase to the Nessie ledger (Nessie balances don't move, so Niche computes the running balance). | `backend/finance/`, `backend/checkout/api.py`, `python -m finance.seed <profile_id>` |
| **Apify (best use, best actor)** | Four actors of our own: `niche-mainstream` (Google Shopping, keeping only stores on our trusted list plus brands you name), `niche-secondhand` (Depop/Poshmark/Vinted/Etsy/Grailed in one labelled, streaming list with sold, promoted and duplicate listings dropped and seller ratings included), and two fully team-built ones that use no community actors: **`niche-indie`** (independent labels' public Shopify catalogs) and **`independent-labels`** (verified independent labels, published-ready with output/dataset schemas). | `backend/actors/` |
| **Bright Data** | Live public web data the product depends on: lookbook imports from public Pinterest, Instagram and TikTok (scrapers, Web Unlocker for boards); finding independent labels on any shop platform (SERP API → Web Unlocker → schema.org product data); verifying that suggested brands are real independents. Public pages only, no logins. | `backend/taste/imports.py`, `backend/sourcing/webshops.py`, `backend/taste/brands.py` |
| **SpacetimeDB** | The real-time backbone: the shared moodboard (owner and friends move pieces together with live cursors), build progress, profile versions that refresh open tabs, and search results streaming in per marketplace as they're scraped and ranked. A server-side `forget_profile` reducer handles Delete my data. | `spacetime/src/index.ts`, `backend/sourcing/live.py` |
| **Cartesia** | Voice is how you talk to Niche: the hands-free assistant on every page listens (Cartesia speech-to-text), cuts at pauses, and replies out loud (Cartesia text-to-speech). Pick from six voices. Spoken onboarding fills the profile form ("I'm Dana, I shop on Depop, budget up to $120"). The key stays on the backend. | `backend/voice/api.py`, `web/components/assistant.tsx` |
| **Moss** | Semantic memory for the agent: every listing you've been shown goes into your own Moss index, so the shop chat recalls "the green skirt from before" without a new search. Saved independent labels' catalogs are indexed too, for millisecond answers while live searches run. | `backend/taste/finds.py`, `backend/taste/labels.py` |
| **Best Use of Gemini** | *Shops near you:* with an opt-in ZIP, Gemini (3.1 Flash-Lite) with **Grounding with Google Maps** finds real independent, vintage and consignment shops worth visiting for each search. Only shops Gemini cites a Maps place for are kept, each with its Google Maps link. Looked up alongside the search in about 3 s. | `backend/taste/nearby.py` |
| **Best Use of Snowflake API** | *Market check:* every listing we see goes into `NICHE.MARKET.LISTINGS` through the **SQL API**, embedded with `AI_EMBED`. Opening a listing finds the ~20 most similar past listings and computes the typical price range, and a **Cortex REST** call (`/api/v2/cortex/inference:complete`) writes a one-line verdict: good deal, fair or above typical. | `backend/market/` |
| **Meta: Bringing People Closer Together** | *Shop for a friend:* share your taste and a friend shops for you using your profile: view-only moodboard, gift chat with your taste and sizes but their budget, revocable links. A shared moodboard with live cursors, and moodboard images for Instagram, TikTok and X. | `/friend`, `/gift`, `backend/taste/api.py` |
| **Microsoft: Built for the Real World / Customer Impact** | A production-minded agent for a real consumer problem: customer understanding (multimodal taste profile), measurable usefulness (impact line per search, market check), responsible design (consent, explanations, scam warnings, delete), end-to-end flow from photos to purchase. 170+ backend tests. | whole repo |

**Not integrated (no code in this repo yet):**
- **Factory Droid SDK:** Droid is not used in the running product.
- **Vultr:** Niche runs locally; it isn't deployed on Vultr.
- **Elastic:** an Elasticsearch index of listings was planned (`docs/CHANGE_LIST.md`), but listing history is in Snowflake and recall in Moss; there is no Elastic code.

---

## Run it

```sh
# API: http://127.0.0.1:8000/docs
cd backend
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
cp .env.example .env            # fill in keys; see the table below
.venv/bin/uvicorn app:create_app --factory --reload --port 8000

# Live state: SpacetimeDB on :3100 (details in spacetime/README.md)
spacetime start --listen-addr 127.0.0.1:3100
cd spacetime && npm install && npm run publish:local

# Web: http://localhost:3000
cd web
cp .env.example .env.local
npm install && npm run dev
```

Everything runs with **no API keys** in fixture mode (`TASTE_MODE=fixture`, `SOURCING_MODE=fixture`). Turn on real services one at a time in `backend/.env`:

| Setting | Enables |
|---|---|
| `TASTE_MODE=live`, `ANTHROPIC_API_KEY` | Claude extraction, taste profile, chat |
| `SOURCING_MODE=live`, `APIFY_TOKEN`, actor names (`MAINSTREAM_ACTOR`, `SECONDHAND_ACTOR`, `INDIE_ACTOR`) | Live marketplace search. Deploy our actors with `python actors/deploy.py` |
| `NICHE_BRIGHTDATA_API_KEY`, `BRIGHTDATA_UNLOCKER_ZONE`, `BRIGHTDATA_SERP_ZONE` | Pinterest/Instagram/TikTok imports; independent web shops |
| `SPACETIME_URL`, `SPACETIME_TOKEN` | Live moodboard and streaming results |
| `CARTESIA_API_KEY` | Voice assistant |
| `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY` | Earlier-finds and label recall |
| `GEMINI_API_KEY` (billing enabled) | Shops near you |
| `SNOWFLAKE_ACCOUNT_URL`, `SNOWFLAKE_PAT`, `SNOWFLAKE_WAREHOUSE` | Market check (then `python -m market.backfill`) |
| `NESSIE_API_KEY`, then `python -m finance.seed <profile_id>` | Budget-aware agent with a demo bank account |

No secrets are committed; `.env` files are git-ignored.

## Tests

```sh
cd backend && .venv/bin/python -m pytest -q
cd web && npx tsc --noEmit && npm run lint
```

## Design

An archival, editorial look: white paper, black ink, grey plinths and 1px rules in Inter Tight. The moodboard is a
ring-bound collage, the profile is an open encyclopedia spread, and the landing letter is a glassine envelope you swipe
open. The footer wordmark is set in Playfair Display italic swashes. Tokens live in `web/app/globals.css`.
