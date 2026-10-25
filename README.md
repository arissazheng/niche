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

```mermaid
flowchart LR
  subgraph Browser["Browser (Next.js)"]
    UI["Taste · Shop · Shortlist pages"]
    VOICE["Assistant dock<br/>hands-free mic + VAD"]
  end
  subgraph API["FastAPI backend"]
    TASTE["Taste engine"]
    SRC["Sourcing pipeline<br/>plan → scrape → filter → rank"]
    CHAT["Shopping chat"]
    VAPI["Voice routes"]
  end
  CLAUDE(["Claude<br/>vision, profile, planner, ranker, chat"])
  APIFY(["Apify actors<br/>mainstream · secondhand · indie"])
  BD(["Bright Data<br/>SERP + Web Unlocker, social imports"])
  CART(["Cartesia<br/>ink-whisper STT · sonic-3 TTS"])
  STDB[("SpacetimeDB<br/>boards, cursors, progress, live results")]
  MOSS[("Moss<br/>per-shopper finds index")]
  SNOW[("Snowflake Cortex<br/>listing history, price check")]
  GEM(["Gemini + Google Maps<br/>shops near you"])
  NESSIE(["Capital One Nessie<br/>budget + purchases"])

  UI -- photos, links, edits --> TASTE --> CLAUDE
  TASTE -- Pinterest, Instagram, TikTok links --> BD
  UI -- search --> SRC
  SRC --> CLAUDE
  SRC --> APIFY
  SRC --> BD
  SRC --> SNOW
  SRC --> GEM
  VOICE -- WAV --> VAPI --> CART
  VOICE -- transcript --> CHAT
  CHAT --> MOSS
  CHAT --> NESSIE
  CHAT --> SRC
  TASTE -- progress, profile version --> STDB
  SRC -- listings as each source lands --> STDB
  STDB -- subscriptions --> UI
  UI -- drag pieces, cursors --> STDB
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
| **Apify (best use, best actor)** | Four actors of our own: `niche-mainstream` (Google Shopping, keeping only stores on our trusted list plus brands you name), `niche-secondhand` (Depop/Poshmark/Vinted/Etsy/Grailed in one labelled, streaming list with sold, promoted and duplicate listings dropped and seller ratings included), and two fully team-built ones that use no community actors: **`niche-indie`** (independent labels' public Shopify catalogs) and **`independent-labels`** (verified independent labels; public on the Apify Store at [apify.com/zaarahemd/independent-labels](https://apify.com/zaarahemd/independent-labels)). | `backend/actors/` |
| **Bright Data** | Live public web data the product depends on: lookbook imports from public Pinterest, Instagram and TikTok (scrapers, Web Unlocker for boards); finding independent labels on any shop platform (SERP API → Web Unlocker → schema.org product data); verifying that suggested brands are real independents. Public pages only, no logins. | `backend/taste/imports.py`, `backend/sourcing/webshops.py`, `backend/taste/brands.py` |
| **SpacetimeDB** | The real-time backbone: the shared moodboard (owner and friends move pieces together with live cursors), build progress, profile versions that refresh open tabs, and search results streaming in per marketplace as they're scraped and ranked. A server-side `forget_profile` reducer handles Delete my data. | `spacetime/src/index.ts`, `backend/sourcing/live.py` |
| **Cartesia** | Voice is how you talk to Niche: the hands-free assistant on every page listens (Cartesia speech-to-text), cuts at pauses, and replies out loud (Cartesia text-to-speech): `ink-whisper` speech-to-text and `sonic-3` voices, six to pick from. Spoken onboarding fills the profile form ("I'm Dana, I shop on Depop, budget up to $120"). The key stays on the backend. | `backend/voice/api.py`, `web/components/assistant.tsx` |
| **Moss** | Semantic memory for the agent: every listing you've been shown goes into your own Moss index, so the shop chat recalls "the green skirt from before" without a new search. Saved independent labels' catalogs are indexed too, for millisecond answers while live searches run. | `backend/taste/finds.py`, `backend/taste/labels.py` |
| **Best Use of Gemini** | *Shops near you:* with an opt-in ZIP, Gemini (3.1 Flash-Lite) with **Grounding with Google Maps** finds real independent, vintage and consignment shops worth visiting for each search. Only shops Gemini cites a Maps place for are kept, each with its Google Maps link. Looked up alongside the search in about 3 s. | `backend/taste/nearby.py` |
| **Best Use of Snowflake API** | *Market check:* every listing we see goes into `NICHE.MARKET.LISTINGS` through the **SQL API**, embedded with `AI_EMBED`. Opening a listing finds the ~20 most similar past listings and computes the typical price range, and a **Cortex REST** call (`/api/v2/cortex/inference:complete`) writes a one-line verdict: good deal, fair or above typical. | `backend/market/` |
| **Meta: Bringing People Closer Together** | *Shop for a friend:* share your taste and a friend shops for you using your profile: view-only moodboard, gift chat with your taste and sizes but their budget, revocable links. A shared moodboard with live cursors, and moodboard images for Instagram, TikTok and X. | `/friend`, `/gift`, `backend/taste/api.py` |
| **Microsoft: Built for the Real World / Customer Impact** | A production-minded agent for a real consumer problem: customer understanding (multimodal taste profile), measurable usefulness (impact line per search, market check), responsible design (consent, explanations, scam warnings, delete), end-to-end flow from photos to purchase. 170+ backend tests. | whole repo |

**Not integrated (no code in this repo yet):**
- **Factory Droid SDK:** Droid is not used in the running product.
- **Vultr:** Niche runs locally; it isn't deployed on Vultr.
- **Elastic:** an Elasticsearch index of listings was planned (`docs/CHANGE_LIST.md`), but listing history is in Snowflake and recall in Moss; there is no Elastic code.

## Sponsor tools in detail

What each sponsor's tool does in the running product, where the code is, and what it doesn't do. Everything here can be checked in the repo. Keys live in `backend/.env` and are never committed.

### Claude (Anthropic)

Claude does the core work. It reads lookbook photos (garments, colours, silhouettes, visible designers), clusters them
into an editable taste profile, applies edits said out loud or typed ("less minimal, more vintage"), plans search
phrases, ranks listings using their photos, and runs the shopping chat. Code: `backend/taste/engine.py`,
`backend/sourcing/claude.py`, `backend/taste/chat.py`.

Where it could go wrong for a shopper, and what we do about it:

| Risk | Guard |
|---|---|
| Misreads a colour from a photo | The palette is measured from pixels (`taste/palette.py`), not taken from Claude |
| Guesses a brand that isn't visible | Brands are only recorded when visible in the image |
| Invents a listing, price or link | Ranked ids are checked against the scraped listings; prices come from the server, never the client |
| Over-applies one trait from the profile | No single pattern or cut fills more than 40% of a page unless asked (`TRAIT_SHARE`) |
| Refuses or fails | Server-side refusal fallback (`fallbacks: "default"`); lexical ranking fallback, labelled on the page |
| Sees photos the shopper didn't agree to share | Photo reactions only run with `data_consent`; "Delete my data" removes photos, records and the live copy |

Every Claude stage logs its system prompt and writes `prompt` and `model_usage` rows to `backend/data/sourcing.sqlite3`.

### Cartesia

The assistant on every page talks and listens hands-free.

- **Speech to text:** `ink-whisper`, via `POST /v1/voice/transcribe` (`backend/voice/api.py`).
- **Speech:** `sonic-3`, via `POST /v1/voice/speak`. Six voices to pick from: Sierra (default), Michelle, Jacqueline,
  Corey, Cooper and Ronald.
- **Listening:** `web/lib/voice-loop.ts` keeps the mic open, detects speech by energy, cuts an utterance after a 1.1 s
  pause, encodes 16 kHz WAV and posts it. The mic pauses while Niche speaks; tap the orb to cut in.
- **What voice does:** setup questions (name, sizes, budget, usual shops are parsed from what you say), reactions to
  photos you upload, reading back your moodboard, edits to your taste profile, and the shopping chat.

Setup: set `CARTESIA_API_KEY` in `backend/.env`. The key stays on the backend; the browser never holds a token.

Responsible use: audio is sent to Cartesia for transcription and isn't saved by Niche. Everything voice can do can
also be typed, so the assistant works without a mic.

Known limitations:

- Energy-based speech detection can mistake loud background noise for speech, or cut a slow speaker off mid-thought.
- Echo cancellation is off (macOS Chrome's voice processing garbled playback), so the mic pauses while Niche speaks
  and you can't talk over it; tap the orb to cut in.
- Each turn is a full request (record, then transcribe, then reply), not streaming, so there is a short gap
  before each answer.

### Apify

All product search runs through Niche's own actors (`backend/actors`): `niche-mainstream` (Google Shopping, kept to
the ~100 stores in our retailer bank), `niche-secondhand` (Depop, Poshmark, Vinted, Etsy; Grailed opt-in) and
`niche-indie` (independent labels' own Shopify stores). The backend runs them for every search, streams each
marketplace's rows in as they finish, and Claude ranks them as one list.

`independent-labels` is a separate public actor on the Apify Store
([apify.com/zaarahemd/independent-labels](https://apify.com/zaarahemd/independent-labels)): brand names or websites in,
verified independent labels and their in-stock products out. It shares its checks with the backend.

Apify doesn't power every feature: lookbook imports and web-wide indie shop discovery use Bright Data, and the price
check uses Snowflake.

### SpacetimeDB

The live layer between the backend's agents and every open browser (`spacetime/src/index.ts`, hosted on SpacetimeDB Maincloud for our demo):

| Live feature | Tables |
|---|---|
| Shared moodboard: friends with the link drag pieces together, with named cursors | `board_piece`, `board_cursor` |
| Build progress while Claude reads your photos ("Reading your images · 6 of 15") | `build_progress` |
| A voice edit, rebuild or other tab updates every open view | `profile_version` |
| Search results stream in per marketplace, then reorder when ranking finishes | `search`, `listing` |
| "Delete my data" also clears the live copy | `forget_profile` reducer |

Without it, the shared board and live cursors don't exist and results arrive all at once after polling. The polling
fallback is there so the backend can be developed without a SpacetimeDB server.

### Visa: reimagining shopping

- **Innovation:** you shop from your own photos and an editable taste profile, not from keywords.
- **Experience:** a friend-like assistant on every page, by voice or text; sizes in your own chart.
- **AI:** Claude plans each search and ranks every listing against your taste, size and budget, and says why each
  result matches.
- **Commerce impact:** small sellers get found. Each results page says how many results came from independent
  labels and secondhand sellers, and you can filter to them.
- **Trust:** no sponsored placements or paid boosts, a visible and editable profile, prices from the server, consent
  before photos go to Claude, delete-my-data. Purchases happen on the seller's own site; Niche doesn't take payments.

### Bright Data

- **Indie shops on any platform** (`backend/sourcing/webshops.py`): the SERP API finds independent shops for a
  search, Web Unlocker reads their pages, and we pull schema.org product data (or a Shopify catalog). This is the only
  way Niche finds small labels that aren't on Shopify. On when `BRIGHTDATA_SERP_ZONE` and `BRIGHTDATA_UNLOCKER_ZONE`
  are set.
- **Lookbook imports** (`backend/taste/imports.py`): public Pinterest, Instagram and TikTok links become lookbook
  photos (outfit photos only, never the person).
- **Real web conditions:** Bright Data's occasional 502 is retried once, a page that fails or times out is skipped,
  and the results page says when the web source was blocked or found nothing, so an empty source never reads as
  "nothing matched".

Public pages only: no logins, no paywalls. A web search takes about 60-80 s, so its results arrive last.

### Moss

Shopping chat memory. Every result a shopper is shown is indexed per shopper (`niche-finds-<profile>`), so "the green
skirt from before" finds it again; saved labels' catalogs go into `niche-indie-labels` (`backend/taste/finds.py`,
`backend/taste/labels.py`). Queries use the Moss SDK (`pip install -e '.[moss]'`) or Moss's cloud query API. Moss is
retrieval, not speech: Cartesia does the voice.

### Capital One Nessie

A budget-aware shopping agent (`backend/finance`). A profile links to a Nessie demo checking account; each chat turn
reads the balance, this month's clothing spend and bills due in the next 14 days, so searches stay inside the monthly
clothing budget and the agent mentions a bill that's due. "Mark as bought" records a purchase to Nessie. Seed a demo
account with `python -m finance.seed <profile_id>`.

### Snowflake

Market price check (`backend/market`). Public listing data (title, brand, price, store, condition, link; never
anything about the shopper) goes into Snowflake. Cortex `AI_EMBED` (arctic-embed-l-v2.0) finds similar past listings,
the "good price / about market / above market" band is computed from their prices, and Cortex writes the one-line
explanation.

### Gemini

"Shops near you" (`backend/taste/nearby.py`): Gemini with Grounding with Google Maps suggests up to four nearby
vintage, consignment and independent shops worth checking for a search. Opt-in; only the ZIP code and the search brief
are sent, and each shop keeps its Google Maps link. Gemini can't see store stock, so these are shops worth a visit, not
shops that have the item.

### Meta: bringing people closer

- **Gift mode** (`/gift/<token>`): shop for a friend using the moodboard link they shared. The agent uses their taste
  and sizes; your budget; their bank and history stay untouched.
- **Shared boards:** friends arrange one moodboard together, live, with named cursors.

### Measuring it

`python -m sourcing.report` (in `backend/`) reads this machine's search log and prints what Niche actually did across
live searches: listings checked, results shown, items left out for wrong size, price or sold, the share of results
from independent labels and secondhand sellers, median time to first listings, and Claude tokens per search. Add
`--json` for the raw numbers. Fixture-mode searches are left out unless you pass `--fixture`.

### Secondhand first

A profile setting (on the setup page). When a resale listing and a new one fit about equally (within 8 points), the
resale one ranks first; a clearly better new piece still wins (`SECONDHAND_NUDGE` in `sourcing/pipeline.py`). The
shortlist shows how many saved pieces are secondhand, from independent labels, or new from big stores. Niche doesn't
estimate carbon or water savings.

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

## Debugging Claude

Every Claude stage (`extract`, `synthesize`, `edit`, `planner`, `ranker`) logs its system prompt to the server log. It also writes `prompt` and `model_usage` rows to the `events` table in `backend/data/sourcing.sqlite3`. Claude calls use server-side refusal fallback (`fallbacks: "default"`).

## Tests

```sh
cd backend && .venv/bin/python -m pytest -q
cd web && npx tsc --noEmit && npm run lint
```

## Design

An archival, editorial look: white paper, black ink, grey plinths and 1px rules in Inter Tight. The moodboard is a
ring-bound collage, the profile is an open encyclopedia spread, and the landing letter is a glassine envelope you swipe
open. The footer wordmark is set in Playfair Display italic swashes. Tokens live in `web/app/globals.css`.
