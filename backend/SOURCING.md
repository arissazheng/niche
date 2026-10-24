# Taste sourcing service

Standalone backend for Person 3: a taste profile and shopping request go in; ranked marketplace listings come out. Apify retrieves listings; Claude plans queries and ranks images/text. No Jev, checkout, payments, voice agent, or profile inference is included.

## Run locally

Python 3.11+ required. From this directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
python -m sourcing examples/search.json --output examples/demo-result.json
uvicorn sourcing.api:create_app --factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs for the interactive API. Default mode is **fixture**: no external calls, no charges, and all items are explicitly synthetic with non-purchasable example.invalid URLs. Fixture ranking is lexical, not Claude. Fixtures intentionally have no product photography.

## Live configuration

Set these values in your local `.env` (never commit it):

```dotenv
SOURCING_MODE=live
APIFY_TOKEN=your-token
ANTHROPIC_API_KEY=your-key
CLAUDE_MODEL=claude-sonnet-4-6
SOURCING_API_KEY=your-private-service-key
```

Use an available Claude model supporting vision and JSON structured outputs. The model ID is configurable. The service refuses live mode without both provider keys. API credentials remain on the server. This project uses direct HTTP provider APIs to keep the integration surface small.

Before live launch, run each source separately with a small candidate limit and inspect real output. The adapters use published Actor contracts, but **no paid live Actor or Claude calls were run during this build**. Marketplace actors are community maintained and can change.

Default Actor mapping, configurable through environment variables:

| Source | Environment variable | Actor |
|---|---|---|
| Etsy | `ETSY_ACTOR` | `one_dollar_store/etsy-listings-scraper` |
| Depop / Poshmark | `RESALE_ACTOR` | `crawlerbros/mercari-poshmark-depop-scraper` |
| Grailed | `GRAILED_ACTOR` | `devilscrapes/grailed-listings-scraper` |

Changing to an Actor with different inputs or outputs also requires updating its adapter. Etsy requires at least 10 requested items; a smaller requested candidate limit is applied when reading its dataset. Grailed supports page counts rather than an item cap: this adapter requests one page and reads at most the requested limit. **Fetched/billed rows can exceed rows read**. Actor spending limits are passed as `maxTotalChargeUsd`; verify their applicability for replacement Actors and pricing models.

## Frontend integration

```sh
curl -X POST http://127.0.0.1:8000/v1/searches \
  -H 'Content-Type: application/json' \
  --data-binary @examples/search.json
```

The 202 response contains `search_id` and `status_url`. Poll that URL every 1–2 seconds. If configured, supply `X-API-Key` from your application backend; do not expose a shared server key in public browser code.

Statuses: `queued`, `running`, `completed`, `partial`, `failed`, `interrupted`. During retrieval, source statuses become available as they finish. Ranked cards appear when ranking completes; partial status means a source or AI stage failed. An empty completed result means no eligible items, not an outage.

Use `results[].image_urls`, `title`, `price`, `currency`, `seller`, `reason`, `warnings`, and `url` for moodboard cards. Render provider strings as text, never HTML. `score` is relative relevance, not probability. `is_fixture` must be visibly identified. Fixture URLs must not be used for purchase flows.

```sh
curl -X POST http://127.0.0.1:8000/v1/searches/SEARCH_ID/feedback \
  -H 'Content-Type: application/json' \
  -d '{"listing_id":"RETURNED_LISTING_ID","liked":true,"comment":"Good silhouette"}'
```

Feedback is persisted for future evaluation; it does not automatically retrain or change a profile.

## Pipeline and tradeoffs

Speed: building a taste profile starts a background warm-up (`sourcing/prefetch.py`) that scrapes and ranks the
profile's core pieces (about 50 s, one extra search's cost). A later search shows matching warm-up items within a few
seconds, then adds live results: each secondhand marketplace is ranked as soon as it finishes, with Etsy (the slowest,
~45 s per page) last. On the free Apify plan (5 runs at once) a search started while the warm-up is still running waits
for free slots.

1. Claude proposes up to three concrete queries. MVP executes one query per source, rotating variants; it does not exhaustively search every query everywhere.
2. Marketplace workers run concurrently. Each run has a timeout and spending setting. Run-start POSTs are not retried because a lost response could otherwise create duplicate paid runs.
3. Normalize, validate marketplace URL, deduplicate IDs/URLs, and apply budget/currency/size/condition/availability rules. Cross-site duplicates are not inferred.
4. Build a source-balanced lexical shortlist of up to 24 items. Claude compares one image per listing and up to three user reference images, using validated JSON outputs. The backend downloads each photo and sends it inline (Claude can't fetch Google Shopping thumbnails by URL), so the server needs outbound access to image hosts; a photo that fails to download makes that listing text-only.
5. Validate returned IDs, scores and explanations. If Claude fails, return a clearly labeled lexical fallback with a warning, never pretend visual ranking succeeded.
6. Return at most two results per seller per marketplace. Seller type remains `unknown`; neither marketplace presence nor model judgment verifies small-business status. Ad flags are retained but never used to boost ranking.

Size matching is case-insensitive exact label matching, not international size conversion or fit prediction. Unknown size, availability, condition (when new-only is requested), or destination shipping are either warned about or excluded by `unknown_policy`. Item price excludes shipping/tax. Ships-from is never interpreted as ships-to. Current adapters do not verify destination shipping. `unknown_policy=exclude` will therefore often return no results.

No second availability check or checkout guarantee exists. `scraped_at` describes retrieval, not inventory reservation. Etsy and Grailed often lack explicit availability and are marked unverified. Raw source data stays in the Apify dataset referenced in each listing's provenance.

## Persistence, operating limits, and debugging

SQLite stores jobs, feedback, source cache and events under `data/`. Normalized retrieval cache lasts five minutes and preserves original timestamps. Jobs process one at a time; source calls within a job are concurrent. Run **one Uvicorn worker / one service instance per database**. This is an MVP worker, not a distributed queue.

Queued jobs resume after restart. Running jobs become `interrupted` instead of replaying potentially chargeable runs. External runs have server-side timeouts; abrupt process termination can leave them running until timeout. Re-submit interrupted searches explicitly. A persistent volume is required to retain the database in containers.

`events` records system prompts/version, model usage, Actor run/dataset IDs, and safe error categories. No API keys or raw user images are logged. User request data, including reference URLs, is retained in the jobs table: use appropriately protected storage and a retention policy before real users. Only system prompts are emitted to server logs.

`MAX_ACTOR_CHARGE_USD` defaults to 0.50 per source run, up to four runs per search. Claude fees and orchestrator compute are additional. The code records token usage, not a guessed dollar total. No automatic purchase or paid deployment occurs.

For public production deployment, add per-user authentication/authorization, request quotas, retention controls, managed job queue, monitoring and source contract checks. The current optional shared API key is suitable for a private team backend; unauthenticated local mode should remain bound to localhost.

## Apify deployment

The `.actor/actor.json` and Dockerfile package the same pipeline as an Actor. Import this directory into your Apify build workflow. Configure `SOURCING_MODE=live`, `ANTHROPIC_API_KEY` as a secret, and the model setting; Apify supplies `APIFY_TOKEN` and default storage IDs at runtime. Paste `examples/search.json` as INPUT.

The Actor writes the full job response to key-value record `OUTPUT` and cards to its default dataset. It exits with an error if all sources failed. Inspect `OUTPUT` for partial failures. Deployment has not been performed or container-tested.

Apify MCP is not required to call Actors. The application uses direct API orchestration. External MCP connectors (e.g. Supabase) are deliberately not required; the JSON API is the integration boundary for your final product.

## Validation

```sh
pytest -q
```

Tests cover the fixture pipeline, strict and permissive unknown handling, sold/price/currency/size/condition filtering, source failure isolation, restart behavior, authentication, feedback validation, invented ranking IDs, mocked Apify/Claude HTTP contracts, caching and Grailed schema mapping. These tests do not establish live scraper reliability or fashion ranking quality.

## References checked during build

- https://apify.com/one_dollar_store/etsy-listings-scraper
- https://apify.com/crawlerbros/mercari-poshmark-depop-scraper
- https://apify.com/devilscrapes/grailed-listings-scraper
- https://docs.apify.com/api/v2/actors-runs-post
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs
