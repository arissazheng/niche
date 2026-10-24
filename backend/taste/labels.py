"""Your labels, kept in Moss: every in-stock product from the independent shops shoppers save goes into one shared
Moss index, so the assistant can answer "something like that Batul slip dress" in milliseconds from the shopper's own
labels while the live searches (seconds to a minute) are still running.

Catalogs come from each shop's public Shopify /products.json, read when a shop is added (and again at most once a day).
Each doc carries what a card needs (title, link, price, photo) as metadata, so a recall needs no second lookup; only
labels the shopper saved are ever returned to them. Reads and writes go through taste/finds.py's Moss plumbing (the
SDK when installed, else the cloud API). Optional like the rest of Moss: no project key means no label recall.
"""
import asyncio
import logging
import re
import time
from actors.niche_actors import indie
from sourcing import safe_fetch
from .brands import catalog
from .finds import Finds

log = logging.getLogger(__name__)
INDEX = 'niche-indie-labels'
REFRESH_SECONDS = 24 * 3600
MAX_DOCS = 400  # per shop
RECALL_SECONDS = 2.5


def docs(shop, products):
    rows = []
    for product in products:
        row = indie.listing(product, shop.model_dump())
        if not row or not row['available'] or not row['url']:
            continue
        text = '. '.join(x for x in [row['title'], product.get('product_type') or '', ' '.join(indie.tags(product)),
                                     f"by {shop.name}", row['description'][:300]] if x)
        rows.append({'id': row['id'], 'text': re.sub(r'\s+', ' ', text)[:1000], 'metadata': {
            'domain': shop.domain, 'title': row['title'][:200], 'url': row['url'], 'price': f"{row['price']:g}",
            'currency': row['currency'], 'image': (row['image_urls'] or [''])[0], 'store': shop.name}})
    return rows[:MAX_DOCS]


class Labels(Finds):
    def __init__(self, settings, store, sdk=None):
        super().__init__(settings, store, sdk)
        self.read_at: dict[str, float] = {}  # domain -> when its catalog was last indexed

    def index_soon(self, shops):
        if not self.on:
            return
        due = [s for s in shops if s.platform == 'shopify' and time.time() - self.read_at.get(s.domain, 0) > REFRESH_SECONDS]
        for shop in due:
            self.read_at[shop.domain] = time.time()
            task = asyncio.create_task(self.index(shop))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def index(self, shop):
        try:
            async with safe_fetch.client() as http:
                batch = docs(shop, await catalog(http, shop.domain))
            if not batch:
                return
            if INDEX not in self.indexes and await self.manage('getIndex', indexName=INDEX) is None:
                await self.manage('createIndex', indexName=INDEX, docs=batch, modelId='moss-minilm')
            else:
                await self.manage('addDocs', indexName=INDEX, docs=batch, options={'upsert': True})
            self.indexes.add(INDEX)
            self.loaded.discard(INDEX)
            self.store.event('labels', 'moss_labels_indexed', {'domain': shop.domain, 'docs': len(batch)})
        except Exception as err:  # Moss is a nice-to-have; try again on the next save or search
            self.read_at.pop(shop.domain, None)
            log.warning('moss label indexing failed for %s: %s', shop.domain, err)

    async def recall_labels(self, shops, text, max_price=None, top_k=4) -> list[dict]:
        """Products from the shopper's own labels that match what they just said."""
        domains = {s.domain for s in shops}
        if not self.on or not domains or not text.strip():
            return []
        try:
            hits = await asyncio.wait_for(self._query(INDEX, text, top_k * 6), RECALL_SECONDS)
        except Exception as err:
            log.warning('moss label recall failed: %s', err)
            return []
        found = []
        for hit in hits:
            meta = hit.get('metadata') or {}
            try:
                price = float(meta.get('price'))
            except (TypeError, ValueError):
                continue
            if meta.get('domain') not in domains or (max_price and price > max_price):
                continue
            found.append({'title': meta.get('title', ''), 'url': meta.get('url', ''), 'price': price,
                          'currency': meta.get('currency', 'USD'), 'store': meta.get('store', ''),
                          'image': meta.get('image', ''), 'score': hit.get('score')})
            if len(found) == top_k:
                break
        return found
