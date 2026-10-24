"""Shared runner: call marketplace scrapers in parallel, normalize, filter, and return one list.

Each marketplace is isolated: a failing scraper is reported in `sources` and the rest still return.
"""
import asyncio
import os
from dataclasses import dataclass
from typing import Callable
from urllib.parse import quote

import httpx

from . import normalize

API = 'https://api.apify.com/v2/'


@dataclass
class Scraper:
    actor: str
    build: Callable  # (queries, items_per_query, max_price) -> list of actor inputs (one run each)
    parse: Callable  # (row) -> listing dict or None
    overfetch: int = 1  # read this many times the requested rows when many get dropped (e.g. Etsy ads)


def price_cap(max_price):
    return {'maxPrice': int(max_price)} if max_price else {}


SCRAPERS = {
    'google_shopping': Scraper('burbn/google-shopping-scraper',
        lambda q, n, p: [{'searchQuery': x, 'country': 'us', 'language': 'en', 'limit': max(10, n), **price_cap(p)}
                         for x in q],
        normalize.google_shopping),
    'depop': Scraper('abotapi/depop-scraper',
        lambda q, n, p: [{'mode': 'search', 'queries': q, 'country': 'us', 'maxPages': 1,
                          'maxListings': n * len(q), **price_cap(p)}],
        normalize.depop),
    'poshmark': Scraper('piotrv1001/poshmark-listings-scraper',
        lambda q, n, p: [{'searchUrls': [f'https://poshmark.com/search?query={quote(x)}&availability=available'
                                         for x in q], 'maxItems': n * len(q), 'maxItemsPerUrl': n}],
        normalize.poshmark),
    'vinted': Scraper('epicscrapers/vinted-search-scraper',
        lambda q, n, p: [{'keywords': q, 'country': 'us', 'maxProducts': n, **price_cap(p)}],
        normalize.vinted),
    'etsy': Scraper('one_dollar_store/etsy-listings-scraper',
        lambda q, n, p: [{'searchTerms': q, 'maxItems': max(10, 2 * n * len(q)), 'maxRunSeconds': 60,
                          **price_cap(p)}],
        normalize.etsy, overfetch=2),
    # $0.20 per run start fee: opt-in only.
    'grailed': Scraper('devilscrapes/grailed-listings-scraper',
        lambda q, n, p: [{'queries': q, 'maxPagesPerQuery': 1}],
        normalize.grailed),
}


def client():
    token = os.environ.get('APIFY_TOKEN')
    # Without a token (local runs behind an injecting proxy) the header is supplied in transit.
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    return httpx.AsyncClient(base_url=API, headers=headers, timeout=200)


async def start_run(http, scraper: Scraper, payload, timeout, wait=90):
    # A lost response is never retried: it could start a second paid run. A refusal for the account's
    # concurrent-run limit (free plan: 5) is retried, because a refused run was never started.
    deadline = asyncio.get_running_loop().time() + wait
    while True:
        response = await http.post(f'acts/{scraper.actor.replace("/", "~")}/runs', params={'timeout': timeout},
                                   json=payload)
        busy = response.status_code == 402 and 'concurrent' in response.text
        if not busy or asyncio.get_running_loop().time() > deadline:
            response.raise_for_status()
            return response.json()['data']
        await asyncio.sleep(3)


async def run_scraper(http, scraper: Scraper, payload, limit, timeout, slots):
    # Start, then poll: long-held sync requests get cut by proxies.
    async with slots:
        run = await start_run(http, scraper, payload, timeout)
        return await finish_run(http, scraper, run, limit, timeout)


async def finish_run(http, scraper: Scraper, run, limit, timeout):
    try:
        async with asyncio.timeout(timeout + 30):
            while run['status'] not in ('SUCCEEDED', 'FAILED', 'TIMED-OUT', 'ABORTED'):
                await asyncio.sleep(2)
                response = await http.get(f'actor-runs/{run["id"]}')
                response.raise_for_status()
                run = response.json()['data']
    except (Exception, asyncio.CancelledError):
        await http.post(f'actor-runs/{run["id"]}/abort')
        raise
    # A timed-out run still keeps what it scraped; use it rather than discard paid rows.
    if run['status'] not in ('SUCCEEDED', 'TIMED-OUT'):
        raise RuntimeError(f'{scraper.actor} finished with {run["status"]}')
    response = await http.get(f'datasets/{run["defaultDatasetId"]}/items',
                              params={'limit': limit, 'clean': 'true', 'format': 'json'})
    response.raise_for_status()
    return response.json()


async def collect(marketplaces, queries, items_per_query=10, max_price=None, timeout=120, parse_options=None,
                  max_concurrent_runs=2):
    queries = [q.strip() for q in queries if q and q.strip()][:3]
    if not queries:
        raise ValueError('At least one query is required')
    parse_options = parse_options or {}
    sources, rows = {}, []
    # Both Niche actors share the account's concurrent-run limit; 2 each plus the 2 parents fits the free plan's 5.
    slots = asyncio.Semaphore(max(1, max_concurrent_runs))

    async def one(name):
        scraper = SCRAPERS[name]
        payloads = scraper.build(queries, items_per_query, max_price)
        limit = max(10, items_per_query * len(queries) * scraper.overfetch) if scraper.overfetch > 1 \
            else items_per_query * len(queries)
        try:
            async with client() as http:
                batches = await asyncio.gather(*(run_scraper(http, scraper, p, limit, timeout, slots)
                                                 for p in payloads))
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get('error', {})
            except ValueError:
                detail = {}
            sources[name] = {'status': 'failed', 'error': f'HTTP {exc.response.status_code}',
                             'type': detail.get('type'), 'message': str(detail.get('message', ''))[:300]}
            return []
        except Exception as exc:
            sources[name] = {'status': 'failed', 'error': type(exc).__name__, 'message': str(exc)[:300]}
            return []
        raw = [r for batch in batches for r in batch]
        parsed = []
        for r in raw:
            try:
                item = scraper.parse(r, **parse_options.get(name, {}))
            except (TypeError, ValueError, AttributeError, KeyError):
                item = None
            if item:
                parsed.append(item)
        sources[name] = {'status': 'succeeded', 'received': len(raw), 'kept': len(parsed), 'actor': scraper.actor}
        return parsed

    for batch in await asyncio.gather(*(one(m) for m in marketplaces)):
        rows.extend(batch)
    return clean(rows, max_price), sources


def clean(rows, max_price=None):
    """Drop ads, over-budget items and duplicates (same id or same link)."""
    seen, result = set(), []
    for row in rows:
        if row['is_ad'] or (max_price and row['price'] > max_price):
            continue
        if row['id'] in seen or row['url'] in seen:
            continue
        seen.update((row['id'], row['url']))
        result.append(row)
    return result
