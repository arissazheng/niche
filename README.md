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

## Prize tracks: criteria and how Niche meets them

For each track: the judging criteria, how Niche addresses each one, then the details (where the code is and what it doesn't do). Keys live in `backend/.env` and are never committed.

### Anthropic: Claude

| Criterion | How Niche meets it |
|---|---|
| **A named community** | People who care about personal style but shop on a student budget, secondhand and from small labels (built by and for Berkeley students like us), whom AI shopping tools currently push toward the same big brands. |
| **A real problem** | We lived it: asking an assistant for "an asymmetrical buttoned top" or "Korean y2k belts like Lewkin" returns sponsored, keyword-stuffed fast fashion, in the wrong size, from stores you never shop. |
| **It works** | One flow done end to end: photos → taste profile → chat search → ranked, explained results in your size and budget → shortlist → buy on the seller's site. Live with real listings; 170+ backend tests. |
| **Thoughtful use of Claude** | Claude does what only it can: reads outfit photos, clusters taste, plans searches, ranks listings by looking at their photos, and talks with you. Where it could go wrong, and our guard for each, is in the risk table below. |

**In detail.** Claude does the core work. It reads lookbook photos (garments, colours, silhouettes, visible designers), clusters them
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


### Visa: Reimagining Shopping with AI

| Criterion | How Niche meets it |
|---|---|
| **Innovation (25%)** | You shop from your own photos and an editable taste profile, not keywords; a friend can shop *for* you from your taste; local shops and a market price check sit next to online results. |
| **User experience (25%)** | A friend-like assistant on every page (voice or text); the agent searches as soon as you ask; compare pieces in chat; sizes in your own chart; a moodboard you can edit and share. |
| **Technical execution (20%)** | Claude plans and visually ranks; four Apify actors plus Bright Data search stores, resale and independent labels in parallel; results stream live through SpacetimeDB; Snowflake checks prices; Nessie budgets. |
| **Commerce impact (15%)** | Small sellers get found: every results page reports listings checked and the share from independent and secondhand sellers; *Secondhand first*; budget-aware search; shortlist → seller's own site → "mark as bought" to Nessie. |
| **Trust & responsibility (15%)** | No sponsored placements; every result explains why; "Before you buy" scam warnings (off-platform payment, too-cheap, poorly reviewed sellers, duplicate listings); consent before photos go to Claude; expiring photo links; Delete my data. |

**In detail.** - **Innovation:** you shop from your own photos and an editable taste profile, not from keywords.
- **Experience:** a friend-like assistant on every page, by voice or text; sizes in your own chart.
- **AI:** Claude plans each search and ranks every listing against your taste, size and budget, and says why each
  result matches.
- **Commerce impact:** small sellers get found. Each results page says how many results came from independent
  labels and secondhand sellers, and you can filter to them.
- **Trust:** no sponsored placements or paid boosts, a visible and editable profile, prices from the server, consent
  before photos go to Claude, delete-my-data. Purchases happen on the seller's own site; Niche doesn't take payments.

#### Measuring it

`python -m sourcing.report` (in `backend/`) reads this machine's search log and prints what Niche actually did across
live searches: listings checked, results shown, items left out for wrong size, price or sold, the share of results
from independent labels and secondhand sellers, median time to first listings, and Claude tokens per search. Add
`--json` for the raw numbers. Fixture-mode searches are left out unless you pass `--fixture`.

#### Secondhand first

A profile setting (on the setup page). When a resale listing and a new one fit about equally (within 8 points), the
resale one ranks first; a clearly better new piece still wins (`SECONDHAND_NUDGE` in `sourcing/pipeline.py`). The
shortlist shows how many saved pieces are secondhand, from independent labels, or new from big stores. Niche doesn't
estimate carbon or water savings.


### Meta: Bringing People Closer Together with AI

| Criterion | How Niche meets it |
|---|---|
| **Strengthens human connection** | Shop for a friend from their shared taste link (a view-only moodboard plus a gift chat using *their* taste and sizes); arrange one moodboard together live with named cursors; share your moodboard to Instagram, TikTok or X. |
| **Essential, well-integrated AI** | Without Claude's taste profile, a friend is guessing; with it, the AI translates someone else's style into pieces you can actually buy for them. |
| **Originality** | Gifting from someone's own taste, not your guess or a gift guide. |
| **Working demo** | Share my taste → open the friend link → "Find something for Arissa" → a real gift search; revoke the link and it stops working. |

**In detail.** - **Gift mode** (`/gift/<token>`): shop for a friend using the moodboard link they shared. The agent uses their taste
  and sizes; your budget; their bank and history stay untouched.
- **Shared boards:** friends arrange one moodboard together, live, with named cursors.


### Microsoft: Built for the Real World / Customer Impact

| Criterion | How Niche meets it |
|---|---|
| **Customer understanding** | The product starts from the customer's own photos, sizes, budget and favourite shops, and asks before acting on its own ideas. |
| **Measurable usefulness** | `python -m sourcing.report` prints listings checked, results shown, items left out for wrong size or price, share from independent and secondhand sellers, time to first results and tokens per search; each page shows its own impact line and market check. |
| **Path from prototype to production** | One FastAPI service with typed models, a fixture mode that runs with no keys, our own deployable Apify actors, cached and retried external calls, and live state in SpacetimeDB (Maincloud for the demo). |
| **Responsible design** | Consent, data minimisation (no name, email, age or ZIP to Claude), explanations, scam warnings, revocable share links, Delete my data. |
| **End-to-end functionality** | Onboarding → lookbook → taste profile → search → shortlist → purchase recorded to a bank ledger, all live. |


### Capital One Nessie

| Criterion | How Niche meets it |
|---|---|
| **Completeness** | Accounts, purchases, bills and merchants: a profile links to a seeded demo checking account; the agent reads balance, this month's clothing spend and upcoming bills; "mark as bought" writes the purchase back. |
| **Creativity** | A shopping agent that respects your actual money: *Keep to budget* caps searches at what's left this month and mentions a bill that's due, without lecturing. |
| **Complexity** | Nessie balances never change, so Niche computes the running balance from purchases; clothing spend is categorised by merchant; purchases are recorded once per item. |

**In detail.** A budget-aware shopping agent (`backend/finance`). A profile links to a Nessie demo checking account; each chat turn
reads the balance, this month's clothing spend and bills due in the next 14 days, so searches stay inside the monthly
clothing budget and the agent mentions a bill that's due. "Mark as bought" records a purchase to Nessie. Seed a demo
account with `python -m finance.seed <profile_id>`.


### Cartesia

| Criterion | How Niche meets it |
|---|---|
| **Problem and originality** | Describing style is easier out loud than in a form: "I'm a medium in tops now", "less minimal, more vintage". |
| **Use of Cartesia** | Voice is core, not an add-on: the hands-free assistant on every page uses `ink-whisper` speech-to-text and `sonic-3` replies (six voices) for onboarding, photo reactions, taste edits and the shopping chat. |
| **Execution** | Pause detection cuts each utterance; the mic pauses while Niche speaks; tap to interrupt; everything also works by typing. |
| **Impact and responsibility** | Accessible without typing; audio isn't stored by Niche; the key stays on the backend. Known limitations are listed below. |

**In detail.** The assistant on every page talks and listens hands-free.

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


### Moss

| Criterion | How Niche meets it |
|---|---|
| **Voice AI** | The Niche assistant listens and acts in real time (with Cartesia), and Moss supplies what it remembers. |
| **Personal agent: remembers you** | Every listing you're shown is indexed per shopper, so "the green skirt from before" comes back instantly; saved labels' catalogs answer "something like that Batul slip dress" in milliseconds while live searches run. |

**In detail.** Shopping chat memory. Every result a shopper is shown is indexed per shopper (`niche-finds-<profile>`), so "the green
skirt from before" finds it again; saved labels' catalogs go into `niche-indie-labels` (`backend/taste/finds.py`,
`backend/taste/labels.py`). Queries use the Moss SDK (`pip install -e '.[moss]'`) or Moss's cloud query API. Moss is
retrieval, not speech: Cartesia does the voice.


### Apify: Best Use / Best Actor

| Criterion | How Niche meets it |
|---|---|
| **Meaningful use** | All product search runs on Apify actors we wrote: without them there are no results. |
| **Project quality** | Results stream per marketplace, are deduplicated and labelled by store type, and are ranked by Claude. |
| **Best actor (built for this event)** | `niche-indie` and `independent-labels` are fully our own code (no community actors inside); `independent-labels` is public on the Apify Store. |

**In detail.** All product search runs through Niche's own actors (`backend/actors`): `niche-mainstream` (Google Shopping, kept to
the ~100 stores in our retailer bank), `niche-secondhand` (Depop, Poshmark, Vinted, Etsy; Grailed opt-in) and
`niche-indie` (independent labels' own Shopify stores). The backend runs them for every search, streams each
marketplace's rows in as they finish, and Claude ranks them as one list.

`independent-labels` is a separate public actor on the Apify Store
([apify.com/zaarahemd/independent-labels](https://apify.com/zaarahemd/independent-labels)): brand names or websites in,
verified independent labels and their in-stock products out. It shares its checks with the backend.

Apify doesn't power every feature: lookbook imports and web-wide indie shop discovery use Bright Data, and the price
check uses Snowflake.


### Bright Data

| Criterion | How Niche meets it |
|---|---|
| **Essential to the core experience** | Remove it and Niche can't find independent labels off Shopify, can't import Pinterest/Instagram/TikTok lookbooks, and can't verify suggested brands. |
| **Real problem, specific user** | Small labels on Squarespace, WooCommerce or Big Cartel are invisible to shopping agents; Bright Data is how a shopper finds them. |
| **Live in the demo; real web conditions** | Live searches every time; 502s retried, slow or blocked pages skipped, and the page says when the web source was blocked or empty. |
| **Right tools, combined** | SERP API to find shops → Web Unlocker to read them → schema.org product data, plus the social scrapers for imports. |
| **Disqualifiers avoided** | Public pages only (no logins or paywalls), no personal data (outfit photos only, never who posted them), no mocked data in the demo. |

**In detail.** - **Indie shops on any platform** (`backend/sourcing/webshops.py`): the SERP API finds independent shops for a
  search, Web Unlocker reads their pages, and we pull schema.org product data (or a Shopify catalog). This is the only
  way Niche finds small labels that aren't on Shopify. On when `BRIGHTDATA_SERP_ZONE` and `BRIGHTDATA_UNLOCKER_ZONE`
  are set.
- **Lookbook imports** (`backend/taste/imports.py`): public Pinterest, Instagram and TikTok links become lookbook
  photos (outfit photos only, never the person).
- **Real web conditions:** Bright Data's occasional 502 is retried once, a page that fails or times out is skipped,
  and the results page says when the web source was blocked or found nothing, so an empty source never reads as
  "nothing matched".

Public pages only: no logins, no paywalls. A web search takes about 60-80 s, so its results arrive last.


### SpacetimeDB

| Criterion | How Niche meets it |
|---|---|
| **Core real-time backend, not on the side** | Live shared state between agents and every open browser: the shared moodboard, build progress, profile versions, and search results streaming in as each marketplace lands. |
| **Multiplayer / instant sync** | Friends with the link drag moodboard pieces together with named cursors; a voice edit in one tab updates every open view. |

**In detail.** The live layer between the backend's agents and every open browser (`spacetime/src/index.ts`, hosted on SpacetimeDB Maincloud for our demo):

| Live feature | Tables |
|---|---|
| Shared moodboard: friends with the link drag pieces together, with named cursors | `board_piece`, `board_cursor` |
| Build progress while Claude reads your photos ("Reading your images · 6 of 15") | `build_progress` |
| A voice edit, rebuild or other tab updates every open view | `profile_version` |
| Search results stream in per marketplace, then reorder when ranking finishes | `search`, `listing` |
| "Delete my data" also clears the live copy | `forget_profile` reducer |

Without it, the shared board and live cursors don't exist and results arrive all at once after polling. The polling
fallback is there so the backend can be developed without a SpacetimeDB server.


### Best Use of Gemini API

| Criterion | How Niche meets it |
|---|---|
| **Pushing what's possible with Gemini** | Gemini with **Grounding with Google Maps** turns a search like "black satin gala dress" plus a ZIP into real nearby vintage, consignment and independent shops worth visiting, which Claude can't do. It runs alongside the search in about 3 s. |

**In detail.** "Shops near you" (`backend/taste/nearby.py`): Gemini with Grounding with Google Maps suggests up to four nearby
vintage, consignment and independent shops worth checking for a search. Opt-in; only the ZIP code and the search brief
are sent, and each shop keeps its Google Maps link. Gemini can't see store stock, so these are shops worth a visit, not
shops that have the item.


### Best Use of Snowflake API

| Criterion | How Niche meets it |
|---|---|
| **LLMs and AI features through the Snowflake APIs** | The **SQL API** stores public listing history and embeds it with Cortex `AI_EMBED`; similar past listings give a typical price range; the **Cortex REST** endpoint (`/api/v2/cortex/inference:complete`) writes the verdict ("good deal", "fair", "above typical"). A retrieval-backed AI feature on one account. |

**In detail.** Market price check (`backend/market`). Public listing data (title, brand, price, store, condition, link; never
anything about the shopper) goes into Snowflake. Cortex `AI_EMBED` (arctic-embed-l-v2.0) finds similar past listings,
the "good price / about market / above market" band is computed from their prices, and Cortex writes the one-line
explanation.


### Not integrated (no code in this repo)

- **Factory Droid SDK:** Droid is not used in the running product.
- **Vultr:** Niche runs locally and isn't deployed on Vultr.
- **Elastic:** an Elasticsearch listing index was planned (`docs/CHANGE_LIST.md`), but listing history is in Snowflake and recall in Moss; there is no Elastic code.

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

Niche is meant to feel like a personal archive of your style rather than another shopping feed. The inspiration is
print and the physical things people keep when they care about clothes:

- **Museum and archive catalogs:** white paper, black ink, grey "plinth" frames around every image, thin 1px rules
  and small uppercase labels, so the clothes are the only colour on the page.
- **Editorial magazines and art books:** generous whitespace, big confident headings and one clean typeface
  (Inter Tight), with a swash italic (Playfair Display) saved for the Niche wordmark.
- **A designer's moodboard:** your taste profile is a ring-bound scrapbook spread, with torn prints, tape, paper
  clips, handwritten cluster names and colour swatches you can rearrange (with friends, live).
- **An encyclopedia:** the profile is an open book with ruled columns, figure plates and page numbers, like an entry
  about you.
- **Stationery:** the landing page's glassine envelope opens to a letter explaining why we built Niche.

Design tokens live in `web/app/globals.css`.
