"""Ingest public listings into Snowflake and price-check a listing against similar past ones.

Only listing data goes in (title, brand, price, store, condition, link): never a profile id or anything about the
shopper. Similarity comes from Cortex embeddings (AI_EMBED) computed in Snowflake; the verdict band is computed here
from the comparables' prices, and Cortex only writes the sentence explaining it.
"""
import asyncio
import json
import logging
import re
from statistics import median
from sourcing.pipeline import item_types
from .snowflake import Snowflake, SnowflakeError

log = logging.getLogger(__name__)

CHUNK = 40  # rows per MERGE statement
NEIGHBOURS = 20
MIN_SIMILARITY = .45  # arctic-embed-l-v2.0 on real listing titles: ~.5-.7 for close pieces; type is matched too
MIN_COMPS = 5

SCHEMA = [
    'CREATE DATABASE IF NOT EXISTS {db}',
    'CREATE SCHEMA IF NOT EXISTS {db}.MARKET',
    '''CREATE TABLE IF NOT EXISTS {db}.MARKET.LISTINGS (
        LISTING_ID STRING PRIMARY KEY, SOURCE STRING, MARKETPLACE STRING, RETAILER STRING, TIER STRING, TITLE STRING,
        BRAND STRING, CATEGORY STRING, CONDITION STRING, PRICE FLOAT, CURRENCY STRING, URL STRING,
        SEEN_AT TIMESTAMP_NTZ, EMBEDDING VECTOR(FLOAT, 1024))''',
]
# CONCAT_WS returns NULL if any part is NULL (e.g. no brand), so each part is coalesced.
EMBED_TEXT = "TRIM(CONCAT_WS(' ', COALESCE({t}.BRAND, ''), COALESCE({t}.TITLE, ''), COALESCE({t}.CATEGORY, '')))"
COLUMNS = ['listing_id', 'source', 'marketplace', 'retailer', 'tier', 'title', 'brand', 'category', 'condition',
           'price', 'currency', 'url']


def secondhand(row):
    return (row.get('source') in ('secondhand',) or row.get('tier') == 'resale'
            or (row.get('condition') or '').lower() not in ('', 'new', 'new with tags', 'nwt'))


def text(row):
    """What the embedding describes: the piece, not the store."""
    return ' '.join(x for x in (row.get('brand'), row.get('title'), row.get('category')) if x)[:400]


def record(listing):
    """A Listing (or its dict) as a row of public listing data."""
    x = listing if isinstance(listing, dict) else listing.model_dump(mode='json')
    category = sorted(item_types(x.get('title') or ''))
    return {'listing_id': str(x['id'])[:200], 'source': x.get('source'), 'marketplace': x.get('marketplace'),
            'retailer': x.get('retailer'), 'tier': x.get('tier'), 'title': (x.get('title') or '')[:300],
            'brand': x.get('brand'), 'category': category[0] if category else None, 'condition': x.get('condition'),
            'price': float(x['price']), 'currency': x.get('currency') or 'USD', 'url': x.get('url')}


def percentile(values, q):
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def band(price, low, high):
    if price < low * .9:
        return 'deal'
    if price > high * 1.1:
        return 'high'
    return 'fair'


class Market:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.db = client or Snowflake(settings)
        self.ready = False
        self.cache: dict[tuple, dict] = {}
        self.pending: set[asyncio.Task] = set()

    @property
    def enabled(self):
        return self.db.enabled

    async def ensure(self):
        if not self.ready:
            for statement in SCHEMA:
                await self.db.sql(statement.format(db=self.settings.snowflake_database), database=False)
            self.ready = True

    def ingest_soon(self, listings):
        """Fire and forget after a search: never slows or fails it."""
        if not self.enabled or not listings:
            return
        task = asyncio.create_task(self._ingest_quietly(listings))
        self.pending.add(task)
        task.add_done_callback(self.pending.discard)

    async def _ingest_quietly(self, listings):
        try:
            await self.ingest(listings)
        except Exception as exc:  # market history is a nice-to-have
            log.warning('snowflake ingest failed: %s', exc)

    async def ingest(self, listings):
        rows = list({r['listing_id']: r for r in map(record, listings)}.values())
        await self.ensure()
        model = self.settings.snowflake_embed_model
        for start in range(0, len(rows), CHUNK):
            chunk = rows[start:start + CHUNK]
            values = ', '.join('(' + ', '.join(['?'] * len(COLUMNS)) + ')' for _ in chunk)
            params = [r[c] for r in chunk for c in COLUMNS]
            cols = ', '.join(c.upper() for c in COLUMNS)
            src = ', '.join(f'column{i + 1} AS {c.upper()}' for i, c in enumerate(COLUMNS))
            await self.db.sql(f'''
                MERGE INTO LISTINGS t USING (SELECT {src} FROM VALUES {values}) s ON t.LISTING_ID = s.LISTING_ID
                WHEN MATCHED THEN UPDATE SET PRICE = s.PRICE, SEEN_AT = CURRENT_TIMESTAMP()
                WHEN NOT MATCHED THEN INSERT ({cols}, SEEN_AT, EMBEDDING) VALUES ({', '.join('s.' + c.upper() for c in COLUMNS)},
                    CURRENT_TIMESTAMP(), AI_EMBED('{model}', {EMBED_TEXT.format(t='s')}))''', params)
        # Self-healing: anything stored without an embedding (e.g. an earlier failed call) gets one now.
        await self.db.sql(f"UPDATE LISTINGS SET EMBEDDING = AI_EMBED('{model}', {EMBED_TEXT.format(t='LISTINGS')}) "
                          'WHERE EMBEDDING IS NULL')
        return len(rows)

    async def comparables(self, row):
        await self.ensure()
        found = await self.db.sql(f'''
            WITH q AS (SELECT AI_EMBED('{self.settings.snowflake_embed_model}', ?) AS v)
            SELECT TITLE, PRICE, MARKETPLACE, RETAILER, TIER, SOURCE, CONDITION, VECTOR_COSINE_SIMILARITY(EMBEDDING, q.v) AS SIM
            FROM LISTINGS, q WHERE CURRENCY = ? AND LISTING_ID <> ? AND EMBEDDING IS NOT NULL
              AND (? IS NULL OR CATEGORY = ?)  -- bags against bags, belts against belts
            ORDER BY SIM DESC LIMIT {NEIGHBOURS}''',
            [text(row), row['currency'], row['listing_id'], row['category'], row['category']])
        comps = [{'title': r[0], 'price': float(r[1]), 'marketplace': r[2] or r[3], 'tier': r[4], 'source': r[5],
                  'condition': r[6], 'similarity': float(r[7])} for r in found if r[7] and float(r[7]) >= MIN_SIMILARITY]
        # Compare like with like when there are enough: secondhand against secondhand, new against new.
        same = [c for c in comps if secondhand(c) == secondhand(row)]
        return same if len(same) >= MIN_COMPS else comps

    async def price_check(self, search_id, listing):
        row = record(listing)
        key = (search_id, row['listing_id'])
        if key in self.cache:
            return self.cache[key]
        unknown = {'verdict': 'unknown', 'n': 0, 'low': None, 'median': None, 'high': None, 'sentence': '',
                   'comparables': []}
        if not self.enabled:
            return unknown
        try:
            comps = await asyncio.wait_for(self.comparables(row), timeout=20)
        except (SnowflakeError, asyncio.TimeoutError, OSError, ValueError) as exc:
            log.warning('snowflake price check failed: %s', exc)
            return unknown
        if len(comps) < MIN_COMPS:
            out = {**unknown, 'n': len(comps),
                   'sentence': "Not enough similar listings yet to say what this usually costs."}
            self.cache[key] = out
            return out
        prices = [c['price'] for c in comps]
        low, mid, high = percentile(prices, .25), median(prices), percentile(prices, .75)
        verdict = band(row['price'], low, high)
        examples = '\n'.join(f"- {c['title'][:80]} · ${c['price']:.0f} · {c['marketplace']}" for c in comps[:6])
        prompt = (
            'You write one short sentence (under 30 words) for a shopper about whether a listing\'s price is a good deal. '
            'Use only the numbers given; never invent prices, brands or facts. Plain text, no quotes.\n'
            f'Listing: {row["title"]} at ${row["price"]:.0f} ({"secondhand" if secondhand(row) else "new"}).\n'
            f'{len(comps)} similar listings: typical ${low:.0f}–${high:.0f}, median ${mid:.0f}.\n'
            f'Verdict already decided from those numbers: {verdict} (deal = below typical, fair = within, high = above).\n'
            f'Some of the similar listings:\n{examples}')
        try:
            sentence = await asyncio.wait_for(self.db.complete(prompt, max_tokens=90), timeout=20)
        except (SnowflakeError, asyncio.TimeoutError, OSError, ValueError) as exc:
            log.warning('cortex verdict failed: %s', exc)
            sentence = ''
        out = {'verdict': verdict, 'n': len(comps), 'low': round(low, 2), 'median': round(mid, 2),
               'high': round(high, 2), 'sentence': re.sub(r'\s+', ' ', sentence).strip()[:300],
               'comparables': [{'title': c['title'], 'price': c['price'], 'marketplace': c['marketplace']}
                               for c in comps[:5]]}
        self.cache[key] = out
        return out


def from_jobs(store):
    """Every listing saved in past searches (for the backfill)."""
    with store.connect() as db:
        rows = [json.loads(r[0] or '{}').get('results') or [] for r in db.execute('SELECT result FROM jobs')]
        rows += [json.loads(r[0] or '[]') for r in db.execute('SELECT payload FROM prefetch')]  # warm-up listings too
    seen = {}
    for items in rows:
        for item in items:
            if isinstance(item, dict) and item.get('id') and item.get('price') is not None:
                seen[item['id']] = item
    return list(seen.values())
