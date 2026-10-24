# Niche Apify actors

Three private actors on the team Apify account. The backend runs all three for every search, merges the rows, and Claude ranks them as one list (`backend/sourcing`).

| Actor | Searches | Labels |
|---|---|---|
| `niche-mainstream` | Google Shopping (`burbn/google-shopping-scraper`), kept only for stores in the retailer bank | store name + type, e.g. `Nordstrom · Department store` |
| `niche-secondhand` | Depop (`abotapi/depop-scraper`), Poshmark (`piotrv1001/poshmark-listings-scraper`), Vinted (`epicscrapers/vinted-search-scraper`), Etsy (`one_dollar_store/etsy-listings-scraper`); Grailed opt-in | `Depop · Secondhand`, `Etsy · Small shop` |
| `niche-indie` | Independent labels' own Shopify stores, read directly from each store's public `/products.json` (no third-party scrapers); seed list in `indie_shops.py`, plus the shopper's own shops (below) | `Christy Dawn · Small shop` |

All three drop sold items, promoted/sponsored listings, items over `maxPrice` and duplicates. Every row has the same fields as the backend `Listing` (`id, marketplace, retailer, tier, title, url, price, currency, image_urls, sizes, condition, brand, seller, ...`).

## Files

- `niche_actors/retailers.py` – the retailer bank. Add a store with one line: name, tier, other names Google Shopping uses for it.
- `niche_actors/normalize.py` – one function per marketplace scraper, mapping its row to the common shape.
- `niche_actors/core.py` – which scraper each marketplace uses and its input; runs them in parallel, isolates failures.
- `niche_actors/mainstream.py`, `secondhand.py`, `indie.py` – the actors' entry points.
- `niche_actors/indie_shops.py` – independent labels niche-indie reads (domain, name, price currency). Add a shop with one line after checking `https://<shop>/products.json` answers.
- `mainstream/.actor`, `secondhand/.actor`, `indie/.actor` – Apify definitions and input forms. `Dockerfile` is shared.
- `deploy.py` – creates or updates the actors on Apify and builds them.

## Run, test, deploy

```sh
cd backend/actors
echo '{"queries":["oversized wool coat"],"maxPrice":200,"itemsPerQuery":10}' > /tmp/in.json
APIFY_TOKEN=... ../.venv/bin/python -m niche_actors.secondhand /tmp/in.json   # runs locally, prints rows (spends credits)
APIFY_TOKEN=... ../.venv/bin/python deploy.py                                 # push code changes to Apify
cd .. && .venv/bin/pytest -q                                                  # offline tests, no credits
```

## Limits and costs (measured 2026-10-24)

- **Free plan: 5 actor runs at once, account-wide.** Each actor starts at most 2 scraper runs at a time (`maxConcurrentRuns`) and waits/retries when Apify refuses for the limit, so both actors fit together. A paid plan raises the limit and makes searches faster.
- Typical search: mainstream ~10 s, secondhand ~50 s (Etsy is the slow one).
- Costs per result on the free plan: Google Shopping **$0.02** ($0.005 on paid plans), Depop ~$0.006, Vinted ~$0.002, Poshmark and Etsy ~$0.001, plus a small start fee per run. Google Shopping returns at least 10 results per phrase, so the backend sends mainstream one phrase × 10 results by default (`MAINSTREAM_QUERIES`, `MAINSTREAM_ITEMS_PER_QUERY`): about $0.23 for mainstream plus ~$0.10 for secondhand per search.
- Mainstream links open Google Shopping's page for the product (which lists the stores selling it), not the store's own product page.
- niche-indie: ~15 s for 35 shops, no per-result cost (only the run's compute). Shopify's edge throttles one IP that
  reads many stores quickly (429, `retry-after: 60`), so it reads 4 shops at a time and waits once on a 429; Apify Proxy
  is tried first if the plan allows it. Catalogs have no search endpoint, so matching happens in the actor: a phrase
  that names an item type (dress, jacket...) only matches that type, a colour alone never matches, and one shop can
  take at most 3 places per phrase.
- Shoppers add their own independent labels on the Taste page (`POST /v1/taste/profiles/{id}/shops`, a brand name or
  website), and favorite brands from onboarding are looked up when the profile builds (`backend/taste/shops.py`). A
  store counts when it answers `/products.json`; a guessed domain also has to call itself by the brand's name in
  `/meta.json`. The backend sends those shops first plus the seed list as the actor's `shops` input, and their names
  join `preferred_stores` for the usual small ranking boost. Only Shopify stores can be read so far.
- Grailed has not been run live yet; it charges $0.20 per run, so it is off by default.
- Community scrapers can change or disappear (the old `crawlerbros` Depop/Poshmark scraper did). If a marketplace starts failing, check `OUTPUT` on the run in the Apify console, then swap the actor in `core.py` and its parser in `normalize.py`.
