# Sponsor tools in Niche

What each sponsor's tool does in the running product, where the code is, and what it doesn't do. Everything here can be
checked in the repo. Keys live in `backend/.env` and are never committed.

## Claude (Anthropic)

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

## Cartesia

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

## Apify

All product search runs through Niche's own actors (`backend/actors`): `niche-mainstream` (Google Shopping, kept to
the ~100 stores in our retailer bank), `niche-secondhand` (Depop, Poshmark, Vinted, Etsy; Grailed opt-in) and
`niche-indie` (independent labels' own Shopify stores). The backend runs them for every search, streams each
marketplace's rows in as they finish, and Claude ranks them as one list.

`independent-labels` is a separate public actor on the Apify Store
([apify.com/zaarahemd/independent-labels](https://apify.com/zaarahemd/independent-labels)): brand names or websites in,
verified independent labels and their in-stock products out. It shares its checks with the backend.

Apify doesn't power every feature: lookbook imports and web-wide indie shop discovery use Bright Data, and the price
check uses Snowflake.

## SpacetimeDB

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

## Visa: reimagining shopping

- **Innovation:** you shop from your own photos and an editable taste profile, not from keywords.
- **Experience:** a friend-like assistant on every page, by voice or text; sizes in your own chart.
- **AI:** Claude plans each search and ranks every listing against your taste, size and budget, and says why each
  result matches.
- **Commerce impact:** small sellers get found. Each results page says how many results came from independent
  labels and secondhand sellers, and you can filter to them.
- **Trust:** no sponsored placements or paid boosts, a visible and editable profile, prices from the server, consent
  before photos go to Claude, delete-my-data. Purchases happen on the seller's own site; Niche doesn't take payments.

## Bright Data

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

## Moss

Shopping chat memory. Every result a shopper is shown is indexed per shopper (`niche-finds-<profile>`), so "the green
skirt from before" finds it again; saved labels' catalogs go into `niche-indie-labels` (`backend/taste/finds.py`,
`backend/taste/labels.py`). Queries use the Moss SDK (`pip install -e '.[moss]'`) or Moss's cloud query API. Moss is
retrieval, not speech: Cartesia does the voice.

## Capital One Nessie

A budget-aware shopping agent (`backend/finance`). A profile links to a Nessie demo checking account; each chat turn
reads the balance, this month's clothing spend and bills due in the next 14 days, so searches stay inside the monthly
clothing budget and the agent mentions a bill that's due. "Mark as bought" records a purchase to Nessie. Seed a demo
account with `python -m finance.seed <profile_id>`.

## Snowflake

Market price check (`backend/market`). Public listing data (title, brand, price, store, condition, link; never
anything about the shopper) goes into Snowflake. Cortex `AI_EMBED` (arctic-embed-l-v2.0) finds similar past listings,
the "good price / about market / above market" band is computed from their prices, and Cortex writes the one-line
explanation.

## Gemini

"Shops near you" (`backend/taste/nearby.py`): Gemini with Grounding with Google Maps suggests up to four nearby
vintage, consignment and independent shops worth checking for a search. Opt-in; only the ZIP code and the search brief
are sent, and each shop keeps its Google Maps link. Gemini can't see store stock, so these are shops worth a visit, not
shops that have the item.

## Meta: bringing people closer

- **Gift mode** (`/gift/<token>`): shop for a friend using the moodboard link they shared. The agent uses their taste
  and sizes; your budget; their bank and history stay untouched.
- **Shared boards:** friends arrange one moodboard together, live, with named cursors.
