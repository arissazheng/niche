"""niche-indie: products from independent fashion labels' own Shopify stores, one labelled list.

Fetches each shop's public catalog (https://<shop>/products.json) directly: no third-party scrapers. Products are
matched to the search phrases here, because Shopify catalogs have no search endpoint.

Input: {"queries": ["black satin midi dress"], "maxPrice": 200, "itemsPerQuery": 10,
        "shops": ["shop.example.com"]}   # optional: overrides the seed list in indie_shops.py
"""
import asyncio
import os
import re

import httpx

from . import normalize
from .indie_shops import SHOPS
from .platform import run

PAGES = 2  # 250 products per page; enough for a label's current collection
AT_ONCE = 4  # Shopify's edge throttles one IP that asks many stores at once
PER_SHOP = 3  # most matches one shop can take per phrase, so one big catalog can't fill the page
USER_AGENT = 'NicheIndieBot/0.1 (+https://github.com/arissazheng/niche; helps shoppers find independent labels)'

# Item types a phrase can ask for; a phrase that names one only matches products of that type.
ITEM_TYPES = {
    'outerwear': r'jackets?|coats?|blazers?|parkas?|puffers?|trench|anoraks?|bombers?|shackets?|gilets?|vests?',
    'knit': r'cardigans?|sweaters?|jumpers?|pullovers?|hoodies?|sweatshirts?|knits?',
    'top': r'tops?|shirts?|tees?|t-shirts?|blouses?|tanks?|camis?|camisoles?|halters?|bodysuits?|polos?|corsets?|bustiers?',
    'dress': r'dress(es)?|gowns?|jumpsuits?|rompers?',
    'bottom': r'pants|jeans|trousers|skirts?|shorts|leggings|culottes',
    'shoes': r'boots?|shoes?|sneakers?|heels?|flats?|loafers?|sandals?|mules?|clogs?|pumps?',
    'bag': r'bags?|purses?|totes?|clutch(es)?|backpacks?|handbags?',
    'accessory': r'belts?|hats?|caps?|beanies?|scarf|scarves|necklaces?|earrings?|rings?|bracelets?|sunglasses',
}
COLOURS = {'black', 'white', 'grey', 'gray', 'charcoal', 'navy', 'blue', 'red', 'green', 'brown', 'beige', 'cream',
           'pink', 'purple', 'yellow', 'orange', 'silver', 'gold', 'tan', 'olive', 'ivory', 'burgundy'}
STOPWORDS = {'and', 'the', 'for', 'with', 'from', 'find', 'some', 'something', 'like', 'that', 'this', 'please',
             'want', 'need', 'looking', 'women', 'womens', 'woman', 'style', 'piece', 'pieces', 'under', 'over'}
SIZE_OPTION = re.compile(r'size|taille|talla', re.I)


def words(text):
    return {w.rstrip('s') for w in re.findall(r'[a-z]+', str(text).lower()) if len(w) > 2 and w not in STOPWORDS}


def item_types(text):
    return {kind for kind, pattern in ITEM_TYPES.items() if re.search(rf'\b({pattern})\b', str(text), re.I)}


def score(phrase, product):
    """How well a product matches a phrase: 0 means no match. It must be the asked-for item type (when one is named)
    and share at least one word that isn't a colour or the type itself; a shared colour only adds to that."""
    text = ' '.join([product.get('title') or '', product.get('product_type') or '', product.get('vendor') or '',
                     ' '.join(tags(product))])
    wanted = item_types(phrase)
    if wanted and not item_types(text) & wanted:
        return 0
    asked, have = words(phrase), words(text)
    type_words = {w for w in asked if item_types(w)}
    features = (asked - COLOURS - type_words) & have
    if not features and not (wanted and type_words & have):
        return 0
    return len(features) * 2 + len(asked & COLOURS & have) + (1 if wanted else 0)


def tags(product):
    value = product.get('tags') or []
    return value.split(',') if isinstance(value, str) else value


def listing(product, shop):
    """One Shopify product as a listing row: the lowest in-stock variant price, size option values, all photos."""
    variants = [v for v in product.get('variants') or [] if isinstance(v, dict)]
    in_stock = [v for v in variants if v.get('available')]
    prices = [p for p in (normalize.money(v.get('price')) for v in in_stock or variants) if p]
    sizes = [value for option in product.get('options') or [] if isinstance(option, dict)
             and SIZE_OPTION.search(option.get('name') or '') for value in option.get('values') or []]
    description = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', product.get('body_html') or '')).strip()
    return normalize.listing('shopify', f'{shop["domain"]}:{product.get("id")}', title=product.get('title'),
        url=f'https://{shop["domain"]}/products/{product.get("handle")}' if product.get('handle') else None,
        price=min(prices) if prices else None, currency=shop.get('currency', 'USD'), retailer=shop['name'],
        tier='small_shop', image_urls=[i.get('src') for i in product.get('images') or [] if isinstance(i, dict)],
        sizes=sizes, condition='new', brand=product.get('vendor') or shop['name'], seller=shop['name'],
        available=bool(in_stock), is_ad=False, description=description[:1000])


def client(proxy=None):
    return httpx.AsyncClient(headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'}, timeout=20,
                             follow_redirects=True, proxy=proxy)


def proxy_url():
    # Apify Proxy, tried only when Shopify throttles the run's own IP (not every plan can reach every shop through it).
    password = os.environ.get('APIFY_PROXY_PASSWORD')
    return f'http://auto:{password}@proxy.apify.com:8000' if password else None


async def get(clients, url, params):
    """Direct first; on Shopify's 429, the proxy if there is one, else one short wait and a retry."""
    response = await clients[0].get(url, params=params)
    if response.status_code == 429:
        if len(clients) > 1:
            try:
                return await clients[1].get(url, params=params)
            except httpx.HTTPError:
                pass
        await asyncio.sleep(min(float(response.headers.get('retry-after') or 5), 10))
        response = await clients[0].get(url, params=params)
    return response


async def catalog(clients, shop):
    products = []
    for page in range(1, PAGES + 1):
        response = await get(clients, f'https://{shop["domain"]}/products.json', {'limit': 250, 'page': page})
        response.raise_for_status()
        batch = response.json().get('products') or []
        products += batch
        if len(batch) < 250:
            break
    return products


async def handle(data, push=None):
    queries = [q for q in data.get('queries') or [] if isinstance(q, str) and q.strip()]
    per_query, cap = data.get('itemsPerQuery', 10), data.get('maxPrice')
    shops = [s if isinstance(s, dict) else {'domain': s, 'name': s} for s in data.get('shops') or SHOPS]
    slots, sources, found = asyncio.Semaphore(AT_ONCE), {}, []

    async def one(clients, shop):
        async with slots:
            try:
                products = await catalog(clients, shop)
            except (httpx.HTTPError, ValueError) as exc:
                sources[shop['domain']] = {'status': 'failed', 'error': type(exc).__name__}
                return
        sources[shop['domain']] = {'status': 'succeeded', 'count': len(products)}
        for product in products:
            row = listing(product, shop)
            if row and row['available'] and not (cap and row['price'] > cap):
                found.append((product, row))

    proxy = proxy_url()
    async with client() as direct, client(proxy) as proxied:
        clients = [direct, proxied] if proxy else [direct]
        await asyncio.gather(*(one(clients, shop) for shop in shops))
    rows, seen = [], set()
    for phrase in queries:
        ranked = sorted(((score(phrase, p), r) for p, r in found), key=lambda x: -x[0])
        taken, per_shop = 0, {}
        for points, row in ranked:
            if points <= 0 or taken >= per_query:
                break
            if row['id'] in seen or per_shop.get(row['retailer'], 0) >= PER_SHOP:
                continue
            seen.add(row['id'])
            per_shop[row['retailer']] = per_shop.get(row['retailer'], 0) + 1
            rows.append(row)
            taken += 1
    return rows, {'actor': 'niche-indie', 'sources': sources, 'count': len(rows),
                  'shops_answered': sum(s['status'] == 'succeeded' for s in sources.values())}


if __name__ == '__main__':
    run(handle)
