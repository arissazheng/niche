import asyncio
import hashlib
import json
from urllib.parse import urlsplit, urlunsplit
import httpx
from .models import Listing
from .store import now

DOMAINS = {'etsy': 'etsy.com', 'depop': 'depop.com', 'poshmark': 'poshmark.com', 'grailed': 'grailed.com'}
# Sources served by Niche's own actors, which take all query variants at once and return normalized rows.
NICHE = ('mainstream', 'secondhand')


def public_url(value, domain=None):
    if not isinstance(value, str):
        return None
    p = urlsplit(value)
    host = (p.hostname or '').lower()
    if p.scheme != 'https' or not host or p.username or p.password:
        return None
    if domain and not (host == domain or host.endswith('.' + domain)):
        return None
    return urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))


def first(row, *keys):
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None


def normalize_niche(source, row, provenance):
    # Rows are already normalized by backend/actors; re-check the link and price rather than trust them.
    url = public_url(row.get('url'))
    try:
        price = float(row.get('price'))
    except (TypeError, ValueError):
        return None
    currency = row.get('currency')
    if not url or not row.get('title') or not (0 <= price < 10000000) or not isinstance(currency, str) or len(currency) != 3:
        return None
    return Listing(id=str(row.get('id') or hashlib.sha256(url.encode()).hexdigest()[:20])[:200], source=source,
        title=str(row['title'])[:500], url=url, image_urls=[x for x in map(public_url, row.get('image_urls') or []) if x][:4],
        description=str(row.get('description') or '')[:2500], price=price, currency=currency.upper(),
        sizes=[str(x) for x in row.get('sizes') or []], condition=row.get('condition'), available=row.get('available'),
        is_ad=row.get('is_ad'), seller=row.get('seller'), shipping_cost=row.get('shipping_cost'),
        marketplace=row.get('marketplace'), retailer=row.get('retailer'), tier=row.get('tier'), brand=row.get('brand'),
        seller_rating=number(row.get('seller_rating'), 5), seller_reviews=number(row.get('seller_reviews')),
        scraped_at=now(), provenance=provenance)


def number(value, most=None):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value < 0 or (most is not None and value > most):
        return None
    return value if most is not None else int(value)


def normalize(source, row, provenance):
    if source in NICHE:
        return normalize_niche(source, row, provenance)
    if row.get('recordType', 'listing') != 'listing':
        return None
    url = public_url(first(row, 'url', 'listingUrl', 'productUrl', 'listing_url', 'link'), DOMAINS[source])
    title = first(row, 'title', 'name', 'productName')
    price = first(row, 'price', 'salePrice', 'currentPrice')
    currency = first(row, 'currency', 'currencyCode')
    if isinstance(price, dict):
        currency = currency or price.get('currency')
        price = price.get('amount')
    try:
        price = float(price)
        if not (0 <= price < 10000000):
            return None
    except (ValueError, TypeError):
        return None
    if not url or not title or not isinstance(currency, str) or len(currency) != 3:
        return None
    images = first(row, 'imageUrls', 'images', 'photos') or [first(row, 'coverImageUrl', 'imageUrl', 'image', 'image_url')]
    if isinstance(images, str):
        images = [images]
    images = [public_url(x.get('url') if isinstance(x,dict) else x) for x in images]
    seller = first(row, 'seller', 'shopName', 'shop_name', 'seller_username')
    if isinstance(seller, dict):
        seller = first(seller, 'username', 'displayName', 'id')
    sizes = first(row, 'sizes', 'size') or []
    if not isinstance(sizes, list):
        sizes = [sizes]
    status = str(row.get('status', '')).lower()
    available = first(row, 'available', 'inStock')
    available = available if isinstance(available, bool) else None
    if status in ('sold', 'sold_out', 'unavailable'):
        available = False
    elif status in ('on_sale', 'active', 'published', 'in_stock') and available is None:
        available = True
    ident = first(row, 'id', 'listingId', 'listing_id')
    canonical = urlunsplit((*urlsplit(url)[:3], '', ''))
    ident = str(ident) if ident is not None else hashlib.sha256(canonical.encode()).hexdigest()[:20]
    return Listing(id=f'{source}:{ident}', source=source, title=str(title)[:500], url=canonical,
        image_urls=[x for x in images if x][:4], description=str(first(row,'fullDescription','description') or '')[:2500],
        price=price, currency=currency.upper(), sizes=[str(x) for x in sizes],
        condition=str(row['condition']) if row.get('condition') else None,
        available=available, is_ad=row.get('isAd') if isinstance(row.get('isAd'),bool) else None, seller=str(seller) if seller else None, scraped_at=now(), provenance=provenance)


class ApifySources:
    def __init__(self, settings, store):
        self.settings, self.store = settings, store

    def actor_input(self, source, query, limit, max_price=None):
        if source in NICHE:
            queries = query if isinstance(query, list) else [query]
            if source == 'mainstream':
                actor, queries = self.settings.mainstream_actor, queries[:self.settings.mainstream_queries]
                per_query = self.settings.mainstream_items_per_query
            else:
                actor, per_query = self.settings.secondhand_actor, max(5, limit // len(queries))
            return actor, {'queries': queries, 'itemsPerQuery': per_query, **({'maxPrice': int(max_price)} if max_price else {})}
        if source == 'etsy':
            return self.settings.etsy_actor, {'searchTerms': [query], 'maxItems': max(10,limit), 'maxRunSeconds': max(5,self.settings.actor_timeout_seconds-10)}
        if source == 'grailed':
            return self.settings.grailed_actor, {'queries': [query], 'maxPagesPerQuery': 1}
        return self.settings.resale_actor, dict(platform=source, mode='searchListings', query=query,
            availableOnly=True, includeSellerProfile=False, includeSellerListings=False, maxItems=limit,
            autoEscalateOnBlock=False)

    async def fetch(self, source, query, limit, job_id, max_price=None):
        listings, status = [], None
        async for batch, status in self.stream(source, query, limit, job_id, max_price):
            listings.extend(batch)
        return listings, status

    async def stream(self, source, query, limit, job_id, max_price=None):
        """Yields (listings, status) as rows land; the last status is final.

        Niche actors push each marketplace's rows as soon as it finishes, so their dataset is read during the run:
        Depop, Poshmark and Vinted show up while Etsy is still scraping. Other actors are read once, at the end."""
        actor, payload = self.actor_input(source, query, limit, max_price)
        key = hashlib.sha256(json.dumps([actor,payload],sort_keys=True).encode()).hexdigest()
        cached = self.store.cached(key)
        if cached:
            yield [Listing.model_validate(x) for x in cached], {'status':'cached', 'count':len(cached)}
            return
        read_limit = limit * (3 if source in NICHE else 1)
        async with httpx.AsyncClient(base_url='https://api.apify.com/v2/',
                headers={'Authorization':f'Bearer {self.settings.apify_token}'}, timeout=30) as client:
            # Never retry a run-start POST: a lost response could otherwise create duplicate charges.
            response = await client.post(f'acts/{actor.replace("/", "~")}/runs', json=payload,
                params={'timeout': self.settings.actor_timeout_seconds, 'maxTotalChargeUsd': self.settings.max_actor_charge_usd})
            response.raise_for_status()
            run = response.json()['data']
            self.store.event(job_id, 'actor_started', {'source':source,'actor':actor,'run_id':run['id']})
            provenance = {'actor_id':actor,'run_id':run['id'],'dataset_id':run['defaultDatasetId']}
            listings, received, dropped = [], 0, 0

            async def read_new():
                nonlocal received, dropped
                response = await client.get(f'datasets/{run["defaultDatasetId"]}/items',
                    params={'clean':'true','offset':received,'limit':read_limit-received,'format':'json'})
                response.raise_for_status()
                rows = response.json()
                received += len(rows)
                batch = []
                for row in rows:
                    try:
                        item = normalize(source,row,provenance)
                    except (ValueError,TypeError,AttributeError):
                        item = None
                    if item:
                        batch.append(item)
                    else:
                        dropped += 1
                return batch

            try:
                async with asyncio.timeout(self.settings.actor_timeout_seconds + 30):
                    while True:
                        finished = run['status'] in ('SUCCEEDED','FAILED','TIMED-OUT','ABORTED')
                        if (finished or source in NICHE) and received < read_limit:
                            batch = await read_new()
                            if batch:
                                listings.extend(batch)
                                yield batch, dict(status='running',count=len(listings),**provenance)
                        if finished:
                            break
                        await asyncio.sleep(2)
                        response = await client.get(f'actor-runs/{run["id"]}')
                        response.raise_for_status()
                        run = response.json()['data']
            except (Exception, asyncio.CancelledError):
                try:
                    await client.post(f'actor-runs/{run["id"]}/abort')
                finally:
                    raise
        # A timed-out run keeps what it scraped.
        if run['status'] not in ('SUCCEEDED', 'TIMED-OUT'):
            raise RuntimeError('Actor finished with ' + run['status'])
        if received and not listings:
            raise RuntimeError('Actor output did not contain usable listings; inspect schema')
        self.store.event(job_id,'source_normalized',dict(source=source,received=received,dropped=dropped,**provenance))
        self.store.cache(key,[x.model_dump(mode='json') for x in listings])
        yield [], dict(status='succeeded',count=len(listings),dropped=dropped,**provenance)


class FixtureSources:
    LABELS = {'mainstream': ('Madewell', 'mainstream', 'new'), 'secondhand': ('Depop', 'resale', 'used')}

    async def fetch(self, source, query, limit, job_id, max_price=None):
        # Deliberately synthetic; never presented as purchasable inventory.
        retailer, tier, condition = self.LABELS.get(source, (source.title(), 'resale', 'used'))
        styles = [('Olive linen wide-leg trousers','olive relaxed linen vintage',48),
                  ('Cream cotton boxy shirt','cream boxy cotton minimal',35),
                  ('Black fitted satin trousers','black fitted satin sleek',65),
                  ('Brown cotton pleated trousers','brown relaxed cotton vintage',55),
                  ('Pink logo skinny trousers','pink skinny logo polyester',120),
                  ('Olive sold trousers','olive relaxed linen',40)]
        rows = [Listing(id=f'{source}:fixture-{i}', source=source,title=title,
            url=f'https://example.invalid/{source}/{i}',description=desc,price=price,currency='USD',
            sizes=['8'],condition=condition,available=i!=5,seller=f'Demo seller {i%3}',retailer=retailer,tier=tier,
            scraped_at=now(),is_fixture=True,provenance={'mode':'fixture'},
            warnings=['Synthetic demo item; not for purchase']) for i,(title,desc,price) in enumerate(styles)]
        return rows[:limit], {'status':'fixture','count':len(rows[:limit])}
