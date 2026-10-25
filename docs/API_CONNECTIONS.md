# API connections

Every outside service the app talks to, what it's for, and the setting that turns it on. Keys go in `backend/.env`
(never committed). Status as of Oct 25.

## Connected and working

| Service | What Niche uses it for | Setting | Status |
|---|---|---|---|
| **Anthropic Claude API** (`api.anthropic.com`, model `claude-opus-5-5`) | Reads lookbook photos, builds the taste profile, edits it, plans search phrases, ranks listings with their photos, shopping chat | `NICHE_ANTHROPIC_API_KEY` (or `ANTHROPIC_API_KEY`) | Live-tested |
| **Apify** (`api.apify.com`) | All product search. Two Niche actors on the `zaarahemd` account: `niche-mainstream` (Google Shopping, ~100 stores) and `niche-secondhand` (Depop, Poshmark, Vinted, Etsy; Grailed opt-in) | `APIFY_TOKEN` | Live-tested; free plan, 5 runs at once |
| **Bright Data** (`api.brightdata.com`) | Lookbook imports from public Pinterest, Instagram and TikTok links (scrapers: Pinterest posts, Instagram posts, Instagram profiles, TikTok posts) | `NICHE_BRIGHTDATA_API_KEY` | Live-tested; $300 promo credits |
| **Capital One Nessie** (`api.nessieisreal.com`) | Mock bank: monthly budget and purchase ledger | `NESSIE_API_KEY`, `NESSIE_ACCOUNT_ID`, `NESSIE_MERCHANT_ID` | Built; "Mark as bought" records purchases to it (purchases happen on the seller's site) |
| **SpacetimeDB** (Maincloud, or a local server) | Live layer: shared moodboard with cursors, build progress, profile sync, results streaming in | `SPACETIME_URL`, `SPACETIME_TOKEN` (backend); `NEXT_PUBLIC_SPACETIMEDB_HOST` (web) | Connected; without it shared boards are off and results arrive by polling |
| **Cartesia** (`api.cartesia.ai`) | The assistant's voice on every page: speech-to-text (`ink-whisper`) and spoken replies (`sonic-3`, six voices) | `CARTESIA_API_KEY` | Live-tested; see the [README](../README.md#cartesia) for limits |
| **Moss** (`service.usemoss.dev`) | Shopping chat memory: semantic search over listings already shown ("the green skirt from before") | `MOSS_PROJECT_ID`, `MOSS_PROJECT_KEY`; SDK via `pip install -e '.[moss]'` | Indexing live-tested; the cloud query API returned 503 on Oct 24-25, so recall needs the SDK |
| **Snowflake** (SQL API + Cortex) | Market price check against similar public listings | `SNOWFLAKE_ACCOUNT_URL`, `SNOWFLAKE_PAT` | Built; off when unset |
| **Gemini** (Grounding with Google Maps) | "Shops near you" under search results (opt-in, ZIP code only) | `GEMINI_API_KEY` | Built; off when unset |

### Apify scrapers behind the two Niche actors

| Marketplace | Apify actor |
|---|---|
| Google Shopping (big stores) | `burbn/google-shopping-scraper` |
| Depop | `abotapi/depop-scraper` |
| Poshmark | `piotrv1001/poshmark-listings-scraper` |
| Vinted | `epicscrapers/vinted-search-scraper` |
| Etsy | `one_dollar_store/etsy-listings-scraper` |
| Grailed (off by default, $0.20 per run) | `devilscrapes/grailed-listings-scraper` |

## Public pages read directly (no key)

| What | Why |
|---|---|
| Product and listing photos (Google Shopping, Etsy, Depop, Poshmark, Vinted images) | Downloaded by the backend and sent to Claude, which can't fetch some of them itself |
| Pinterest board RSS feeds | Public board import, free and fast |
| TikTok oEmbed, Pinterest pin pages | Fast cover image for a single TikTok or pin before falling back to Bright Data |
| Product pages pasted into the shopping chat | Title and photo for "find something like this" |

All of these go through `sourcing/safe_fetch.py` (public addresses only, size-capped).

## Set up but not connected yet

| Service | Needed for | What's missing |
|---|---|---|
| **Elastic** (Elasticsearch Serverless) | Instant search over every listing found so far | Project URL and API key |
| **Fetch.ai** (Agentverse / ASI:One) | Niche as a shopping agent inside ASI:One | Agentverse account and API key |

## Removed

- **Stripe**: taken out with checkout on hold.
