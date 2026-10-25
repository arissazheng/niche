# Sponsor tools in Niche: criteria and how we meet them

The same content is in the [README](README.md#prize-tracks-criteria-and-how-niche-meets-them); keep the two in sync.

For each track: the judging criteria, how Niche addresses each one, then the details (where the code is and what it doesn't do). Keys live in `backend/.env` and are never committed.

## Anthropic: Claude

**1. A named community.** **Small clothing sellers (independent labels, Depop and Poshmark resellers, vintage and
thrift shops) and the Berkeley students who buy from them:** people who dress in a specific aesthetic (y2k, office
siren, grunge) and shop secondhand and from Instagram-native labels on a student budget. Not "students" or "shoppers":
a specific set of buyers, and the long tail of sellers they want to find.

**2. A real problem.** **We lived it: agentic search doesn't fit the shopper, and it leaves most sellers behind.**
Real shoppers don't write paragraph-long prompts describing their exact style, size and budget. They type a few words
("a cute top for a date"). With so little to go on, agentic search falls back on what it's financially incentivised to
show: partner brands (retailers are already striking deals with AI companies, like Target with OpenAI) and the biggest,
most keyword-stuffed catalogs. The shopper gets things they wouldn't actually buy, and the wide range of clothing
sellers whose pieces would have fit never appears. Niche fixes the input side too: your photos and taste profile say
what a paragraph-long prompt would, so a short request is enough. We tried today's AI assistants with the kind of short prompts real shoppers type:
- **ChatGPT**, "Find 5 outfits for my next week.": searched 30 retailers, then suggested only Target.
- **ChatGPT**, "Now try secondhand.": cited a Harvard paper on eating disorders and an Ohio government website.
- **Gemini and Grok**, "Help me find clothes.": Urban Outfitters, ASOS, Forever 21, Uniqlo. No one small, no one secondhand.

**3. It works.** **One thing done well: your own outfit photos in, a short list of real, buyable pieces out, in your
size and budget, from any seller big or small, each with the reason it fits.** It runs today against live listings
from independent labels, resale marketplaces, local shops and major retailers, with real Claude ranking (nothing
mocked), and you buy on the seller's own site. Voice, sharing and the price check all serve that one flow.

**4. Thoughtful use of Claude.** **What it does that matters:** Claude is what makes fair representation possible. It
judges every listing on its merits (the photo against the shopper's taste, the request and their size) instead of on
which brand is promoted or how a search engine ordered it, so a one-person Depop shop or an independent label can
outrank a partner brand when it's the better fit. It also turns photos into a taste profile and a request into search
phrases, and it is told never to favour a store or brand unless the shopper asked for it.

**Where it could go wrong for these shoppers, and what we do about it:**
- *Wrong size*: hard size filter per category, size checks in titles, "Size unverified" caveat when unknown.
- *Misreads a colour*: colours are measured from pixels (skin and background excluded), not taken from Claude.
- *Over-applies the taste profile*: no single trait fills more than 40% of a page; the request's features must be visible or the item is dropped.
- *Invents a listing or price*: ranked ids are checked against scraped listings; prices come from the server.
- *Can't spot a scam*: rule-based "Before you buy" warnings (off-platform payment, too-cheap, poorly reviewed or duplicated sellers).
- *Sees more than it should*: consent before any photo goes to Claude; name, email, age and ZIP are never sent.
- *Refuses or is down*: server-side refusal fallback, and a labelled keyword-ranking fallback.

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


## Visa: Reimagining Shopping with AI

| Criterion | How Niche meets it |
|---|---|
| **Innovation (25%)** — how creatively does it reimagine shopping? | Shopping starts from your own photos and an editable taste profile instead of keywords; a friend can shop *for* you from your taste; local shops (Gemini + Maps) and a market price check (Snowflake) sit next to online results. |
| **User experience (25%)** — intuitive, useful, seamless? | A hands-free assistant on every page; the agent searches as soon as you ask and asks first only for its own ideas; results stream in; compare pieces in chat ("#2 or #5?"); sizes in your own chart; one shortlist to buy from. |
| **Technical execution (20%)** — how effectively are AI and supporting tech used? | Claude plans and visually ranks; four Apify actors plus Bright Data search stores, resale and independent labels in parallel; SpacetimeDB streams results live; Snowflake Cortex checks prices; Nessie keeps the agent on budget. 170+ backend tests; fixture mode runs with no keys. |
| **Commerce impact (15%)** — engagement, conversion, loyalty or merchant outcomes? | *Merchant outcomes:* independent and secondhand sellers are surfaced without paying for placement, and every results page reports their share. *Conversion:* fewer, better-fitting results in your size and budget, a shortlist, and the seller's own checkout. *Engagement and loyalty:* the profile learns from what you save; the moodboard and friend sharing bring people back. |
| **Trust & responsibility (15%)** — privacy, transparency, security, responsible AI? | *Privacy:* consent before photos go to Claude, minimal data sent, Delete my data, revocable share links. *Transparency:* no sponsored placements, a reason on every result, a plain-language "How Niche ranks" page. *Security:* expiring signed photo links, prices from the server, safe fetching that blocks private addresses. *Responsible AI:* scam warnings, honest caveats, the risk table in the Anthropic section. |

**In detail.** - **Innovation:** you shop from your own photos and an editable taste profile, not from keywords.
- **Experience:** a friend-like assistant on every page, by voice or text; sizes in your own chart.
- **AI:** Claude plans each search and ranks every listing against your taste, size and budget, and says why each
  result matches.
- **Commerce impact:** small sellers get found. Each results page says how many results came from independent
  labels and secondhand sellers, and you can filter to them.
- **Trust:** no sponsored placements or paid boosts, a visible and editable profile, prices from the server, consent
  before photos go to Claude, delete-my-data. Purchases happen on the seller's own site; Niche doesn't take payments.

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


## Meta: Bringing People Closer Together with AI

| Criterion | How Niche meets it |
|---|---|
| **How meaningfully it strengthens human connection** | Shopping for someone you care about, using *their* taste: share your taste link, a friend sees your view-only moodboard and finds a gift in your style and sizes on their budget. Friends can arrange one moodboard together, live, with named cursors. Sharing your style is one click: Niche renders your moodboard as a story or square image and drafts the post for you on X, ready to post with the image attached; for Instagram and TikTok it downloads the image and opens the upload page. |
| **How essential and well-integrated the AI is** | Without Claude's taste profile the friend is guessing; with it, the AI translates someone else's style into specific pieces. The same agent, ranking and safety checks run in gift mode. |
| **Originality** | Gifting from someone's own photos and taste rather than a gift guide or your own guess. |
| **Strength of the working demo** | Live on one laptop: Share my taste → open the friend link in a new tab → "Find something for Arissa" → a real gift search with real listings → Stop sharing, and the link is dead. |

**In detail.** - **Gift mode** (`/gift/<token>`): shop for a friend using the moodboard link they shared. The agent uses their taste
  and sizes; your budget; their bank and history stay untouched.
- **Shared boards:** friends arrange one moodboard together, live, with named cursors.


## Microsoft: Built for the Real World / Customer Impact

| Criterion | How Niche meets it |
|---|---|
| **Track challenge** — a production-minded AI agent for a meaningful problem in a high-impact domain | Fair representation in agentic commerce. As people shop through AI agents, those agents return whatever their search engines promote (paid placements and the biggest, most keyword-stuffed catalogs), so independent and secondhand businesses go unseen no matter how well they fit. Niche is a shopping agent (with a finance side through Nessie budgets) that returns the best results for the user's own preferences: right size, right style, inside budget, from any seller, big or small. |
| **Customer understanding** | Built from how our community actually shops (see the Anthropic section): own photos, specific aesthetics, secondhand first, tight budgets, hard-to-find sizes. The agent asks before acting on its own ideas. |
| **Measurable usefulness** | `python -m sourcing.report` reports, across live searches: listings checked, results shown, items removed for wrong size, price or sold, share of independent and secondhand results, time to first results, Claude tokens per search. Each results page shows its own impact line. |
| **Path from prototype to production** | One FastAPI service with typed models and tests; fixture mode with no keys; our own deployable Apify actors; caching, retries and timeouts on every external call; SpacetimeDB Maincloud for live state. Deployed at [shopniche.fashion](https://shopniche.fashion). |
| **Responsible design** | Consent, data minimisation, explanations, scam warnings, revocable sharing, Delete my data (see Visa trust row). |
| **End-to-end functionality** | Onboarding → lookbook → taste profile → search → shortlist → seller's site → purchase recorded to the bank ledger, all running live. |


## Capital One Nessie

| Criterion | How Niche meets it |
|---|---|
| **Completeness** | Customers, accounts, merchants, purchases and bills are all used: a seed script creates a demo customer with a month of history and two upcoming bills; the agent reads balance, clothing spend and bills each turn; "mark as bought" records a purchase, once per item. |
| **Creativity** | A shopping agent that respects real money: *Keep to budget* caps searches at what's left of the monthly clothing budget and mentions a bill due soon, in a sentence, without lecturing. |
| **Complexity** | Nessie balances never change, so Niche computes the running balance from purchases; spend is categorised by merchant; Nessie quirks (https only, whole dollars, immutable purchases, required bill dates) are handled. |

**In detail.** A budget-aware shopping agent (`backend/finance`). A profile links to a Nessie demo checking account; each chat turn
reads the balance, this month's clothing spend and bills due in the next 14 days, so searches stay inside the monthly
clothing budget and the agent mentions a bill that's due. "Mark as bought" records a purchase to Nessie. Seed a demo
account with `python -m finance.seed <profile_id>`.


## Cartesia

| Criterion | How Niche meets it |
|---|---|
| **Problem and originality (25%)** — useful, clearly scoped, thoughtfully designed? | Style is easier to say than to type into a form: "I'm a medium in tops now", "less minimal, more vintage", "find me something like that". Voice runs one scoped job: a friend-like stylist you talk to while you browse. |
| **Use of Cartesia (25%)** — core, not added on; voice clear, responsive and natural? | Voice is the main way to use the assistant on every page: `ink-whisper` speech-to-text and `sonic-3` replies with six voices to choose from. It drives onboarding (spoken answers fill the form), reactions to new photos, taste-profile edits and the shopping chat. |
| **Execution (25%)** — does the main flow work; edge cases handled? | Hands-free listening cuts at 1.1 s pauses; the mic pauses while Niche speaks so it doesn't hear itself; tap to interrupt; "no" and corrections are understood; a failed transcription asks again; everything also works by typing. |
| **Impact and responsibility (25%)** — accessibility, privacy, responsible use? | Usable without typing; audio is transcribed and not stored by Niche; the Cartesia key never reaches the browser. |
| **What to submit:** working demo, 2-minute demo-first presentation | Demo flow: talk through onboarding → photos → "find me…" by voice → results. |
| **What to submit:** README with setup, Cartesia features used, known limitations | Setup (`CARTESIA_API_KEY`), features and known limitations are in the details below. |
| **What to submit:** source access, no keys or secrets in the repo | Public repo; keys only in git-ignored `.env` files. |

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


## Moss

| Criterion | How Niche meets it |
|---|---|
| **1. Voice AI** — agents that listen, respond and act in real time | The Niche assistant listens and answers by voice (Cartesia) and acts: it runs searches, edits the profile and saves pieces. Moss is its memory, so it can answer from earlier finds instantly instead of starting a new search. |
| **2. Personal agent** — remembers you, works across your apps, handles everyday tasks | *Remembers you:* every listing you're shown goes into your own Moss index ("the green skirt from before"), and saved labels' catalogs answer "something like that Batul slip dress" in milliseconds. *Across apps / everyday tasks:* it pulls from your Pinterest, Instagram and TikTok saves and keeps shopping within your bank budget. It does not act in other apps on its own. |
| **3. Social post** — best engagement | Not a Moss feature here. Niche does turn moodboards into posts for Instagram, TikTok and X, but that doesn't use Moss. |

**In detail.** Shopping chat memory. Every result a shopper is shown is indexed per shopper (`niche-finds-<profile>`), so "the green
skirt from before" finds it again; saved labels' catalogs go into `niche-indie-labels` (`backend/taste/finds.py`,
`backend/taste/labels.py`). Queries use the Moss SDK (`pip install -e '.[moss]'`) or Moss's cloud query API. Moss is
retrieval, not speech: Cartesia does the voice.


## Apify: Best Use / Best Actor

| Criterion | How Niche meets it |
|---|---|
| **Top 5 using Apify in a meaningful way** | All product search runs on actors we wrote; remove Apify and there are no results. Each search calls the mainstream, secondhand and indie actors in parallel and streams rows as each marketplace finishes. |
| **Quality of the project** | See the Anthropic, Visa and Microsoft sections: live, end to end, tested. |
| **Best actor built for this event** | `niche-indie` and `independent-labels` are our own code end to end (no community actors inside); `independent-labels` is public on the Apify Store with input, output and dataset schemas. `niche-mainstream` and `niche-secondhand` are our own aggregation actors built on community scrapers. |

**In detail.** All product search runs through Niche's own actors (`backend/actors`): `niche-mainstream` (Google Shopping, kept to
the ~100 stores in our retailer bank), `niche-secondhand` (Depop, Poshmark, Vinted, Etsy; Grailed opt-in) and
`niche-indie` (independent labels' own Shopify stores). The backend runs them for every search, streams each
marketplace's rows in as they finish, and Claude ranks them as one list.

`independent-labels` is a separate public actor on the Apify Store
([apify.com/zaarahemd/independent-labels](https://apify.com/zaarahemd/independent-labels)): brand names or websites in,
verified independent labels and their in-stock products out. It shares its checks with the backend.

Apify doesn't power every feature: lookbook imports and web-wide indie shop discovery use Bright Data, and the price
check uses Snowflake.


## Bright Data

| Criterion | How Niche meets it |
|---|---|
| **Essential to the core experience** — would it stop working without live web data? | Search itself still runs on Apify without it, so we don't claim the whole product depends on Bright Data. What does: lookbook imports from Pinterest, Instagram and TikTok; finding independent labels that aren't on Shopify; checking that suggested brands are real independents. Without Bright Data those disappear. |
| **A clear, real-world problem for a specific user** | Small labels on Squarespace, WooCommerce or Big Cartel are invisible to shopping agents; our community shops exactly those brands. |
| **Runs live in the demo** | Yes: imports and web-shop discovery run live on every search. |
| **Handles blocks, slow responses and empty results** | 502s retried once; failing or slow pages skipped with timeouts; the results page says when the web source was blocked or found nothing, so it never reads as "nothing matched". |
| **Turns raw data into clean, useful output** | SERP results → shop pages → schema.org product data → the same listing format as every other source, then filtered and ranked by Claude. |
| **Extra credit:** right tools, combined thoughtfully; a clear 2-minute story with real results | SERP API to find shops, Web Unlocker to read them, social scrapers for imports, each where it fits. Demo: paste an Instagram profile → its outfits join your lookbook; search → a non-Shopify label appears in results. |
| **Disqualifiers** — login/paywall scraping, non-public personal data, mocked data, README-only | Public pages only; outfit photos only, never who posted them; no mocked data in the demo; used in the running product. |

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


## SpacetimeDB

| Criterion | How Niche meets it |
|---|---|
| **Spacetime as the core real-time backend** | It is the live layer between the backend's agents and every open browser: moodboard state, build progress, profile versions and streaming search results all live in the module. |
| **Live shared state, multiplayer, instant sync between users / agents / systems** | *Users:* friends drag moodboard pieces together with named cursors. *Agents → users:* listings stream in per marketplace as the search agent finds them, then reorder when ranking finishes. *Systems:* a voice edit or rebuild updates every open view. |
| **Meaningfully used, not on the side** | Without it there is no shared moodboard, no live cursors and no streaming results; server-side reducers (including `forget_profile` for Delete my data) run next to the data. |

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


## Best Use of Gemini API

| Criterion | How Niche meets it |
|---|---|
| **Push the boundaries of what's possible with Gemini** | Gemini with **Grounding with Google Maps** does something Claude can't: it turns a search ("black satin gala dress") plus a ZIP into real nearby vintage, consignment and independent shops worth visiting, each with its Maps link. Shops without a Maps citation are dropped. It runs alongside the search and returns in about 3 s. |

**In detail.** "Shops near you" (`backend/taste/nearby.py`): Gemini with Grounding with Google Maps suggests up to four nearby
vintage, consignment and independent shops worth checking for a search. Opt-in; only the ZIP code and the search brief
are sent, and each shop keeps its Google Maps link. Gemini can't see store stock, so these are shops worth a visit, not
shops that have the item.


## Best Use of Snowflake API

| Criterion | How Niche meets it |
|---|---|
| **Use industry-leading LLMs on a single account through the Snowflake APIs** | Two Snowflake REST APIs from one account: the **SQL API** stores public listing history and embeds it with Cortex `AI_EMBED`; the **Cortex REST** inference endpoint (`/api/v2/cortex/inference:complete`, `claude-sonnet-4-5`) writes each verdict. |
| **Build apps, RAG-powered chatbots or AI-powered features** | An AI-powered, retrieval-backed feature: opening a listing retrieves the ~20 most similar past listings, computes the typical price range, and Cortex explains whether it's a good deal, fair or above typical, grounded only in those numbers. |

**In detail.** Market price check (`backend/market`). Public listing data (title, brand, price, store, condition, link; never
anything about the shopper) goes into Snowflake. Cortex `AI_EMBED` (arctic-embed-l-v2.0) finds similar past listings,
the "good price / about market / above market" band is computed from their prices, and Cortex writes the one-line
explanation.


## Not integrated (no code in this repo)

- **Factory Droid SDK:** Droid is not used in the running product.
- **Vultr:** Niche isn't hosted on Vultr.
- **Elastic:** an Elasticsearch listing index was planned, but listing history is in Snowflake and recall in Moss; there is no Elastic code.
