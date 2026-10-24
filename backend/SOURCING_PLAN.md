# Person 3 implementation and handoff plan

## Scope implemented

- Independent Python backend: shared core callable from CLI, FastAPI, or Apify Actor.
- Versioned input profile, shopping constraints, common listing contract.
- Configurable Etsy, Depop, Poshmark and Grailed adapters based on published schemas.
- Claude query planner and multimodal ranker with structured outputs and local validation.
- Source-isolated retrieval, canonical deduplication, hard filters, explicit unknowns, seller diversity.
- Async HTTP jobs, SQLite persistence, five-minute source cache, feedback collection, usage/provenance events.
- Offline fixtures, sample requests/results, Docker/Actor packaging, contract and integration tests.

## Next: credentialed validation

1. Put Apify and Claude credentials in `.env` on the server.
2. Run Etsy and Depop separately with small limits; inspect source datasets, normalized fields and charges.
3. Run Poshmark and Grailed the same way. Replace an Actor if its actual response contract or reliability differs.
4. Run three contrasting profiles against live data; inspect Claude explanations, images, constraints and token usage.
5. Share the API URL and generated OpenAPI contract with frontend teammates. Test loading, partial failures, no matches and feedback.
6. Deploy privately with a persistent database volume and a server API key. Use one worker.

## Product evaluation before public release

Collect user relevance ratings for 200–300 profile/listing pairs. Measure liked-item retrieval coverage, top-10 relevance, source success, stale inventory, unknown size/shipping coverage, latency, cost, and seller diversity. The lexical shortlist can suppress visually relevant items: compare it against ranking a larger candidate set before making quality claims.

## Follow-up improvements

- Item detail/availability refresh and richer size/shipping extraction.
- Explicit seller verification or a curated independent-seller directory.
- Multiple queries per source under a total budget, incremental results, retry policies for safe reads.
- Embedding-based retrieval if lexical recall is inadequate.
- Per-user auth, durable distributed queue, rate limiting and deletion/retention controls.
- Optional database connector if the team selects Supabase or another shared backend.

## Deferred

Jev experimentation, checkout, Stripe Link, Nessie, account onboarding, voice conversation, taste-profile inference, social imports, and final moodboard UI. Purchase integration must establish merchant/marketplace support separately; a scrapeable listing is not automatically checkout-compatible.
