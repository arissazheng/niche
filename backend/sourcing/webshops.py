"""Independent labels on any shop platform, found and read through Bright Data.

niche-indie reads Shopify catalogs it already knows. This finds the rest: Bright Data's SERP API searches Google for
the request ("black satin midi dress independent designer"), big retailers and marketplaces are dropped, and each
remaining page is read through the Web Unlocker (which gets past bot blocks) for the schema.org Product data that
Squarespace, WooCommerce, Big Cartel, Wix and Shopify stores all publish. The shopper's own non-Shopify shops are
searched the same way, with `site:<domain>`.

Costs: about 2-3 SERP requests and up to MAX_PAGES unlocked pages per search (Bright Data bills per request).
"""
import asyncio
import hashlib
import html
import json
import re
from urllib.parse import quote_plus, urlsplit, urlunsplit
import httpx
from actors.niche_actors import indie
from actors.niche_actors.labels import host, independent  # shared with the independent-labels actor
from .models import Listing
from .store import now

API = 'https://api.brightdata.com/'
MAX_PAGES = 12
PAGE_SECONDS = 45  # a slow page is skipped, so the source finishes within about two minutes
AT_ONCE = 6
# Kept out of the Google searches themselves, so their results leave room for labels' own sites.
EXCLUDE = ''.join(f' -site:{d}' for d in ('amazon.com', 'etsy.com', 'ebay.com', 'pinterest.com', 'instagram.com',
                                           'facebook.com', 'youtube.com', 'nordstrom.com'))
# Articles and guides, not shop pages.
ARTICLE = re.compile(r'/(blogs?|features?|articles?|tag|news|journal|stories|guides?|board|editorial)/', re.I)
SHOPIFY = re.compile(r'cdn\.shopify\.com|/cdn/shop/|Shopify\.theme')
# Links that look like a single product on the common shop platforms (Shopify, Wix, WooCommerce, Squarespace...).
PRODUCT_LINK = re.compile(r'href=["\']((?:https://[^"\'/]+)?/(?:products|product|product-page|shop/p|p)/[^"\'#?]+)["\']', re.I)
PRODUCT_TYPES = {'product', 'productgroup', 'individualproduct'}


def queries_for(query, shops=()):
    """Google searches: the request among small labels, plus each of the shopper's own non-Shopify shops."""
    found = [f'{query} independent designer label{EXCLUDE}', f'{query} "slow fashion" brand shop{EXCLUDE}']
    return found + [f'site:{s.domain} {query}' for s in shops][:6]


def json_ld(page):
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            yield json.loads(html.unescape(block.strip()))
        except ValueError:
            continue


def walk(node):
    """Every dict in a JSON-LD tree (@graph, lists, ItemList elements, ProductGroup variants...)."""
    if isinstance(node, list):
        for x in node:
            yield from walk(x)
    elif isinstance(node, dict):
        yield node
        for key in ('@graph', 'itemListElement', 'item', 'hasVariant', 'mainEntity'):
            if key in node:
                yield from walk(node[key])


def kind(node):
    value = node.get('@type')
    values = value if isinstance(value, list) else [value]
    return {str(v).lower() for v in values}


def text(value):
    if isinstance(value, dict):
        value = value.get('name') or value.get('@id')
    if isinstance(value, list):
        value = value[0] if value else None
    return html.unescape(str(value)).strip() if value else None


def images(value):
    values = value if isinstance(value, list) else [value]
    out = []
    for v in values:
        v = v.get('url') or v.get('contentUrl') if isinstance(v, dict) else v
        if isinstance(v, str) and v.startswith('//'):
            v = 'https:' + v
        if isinstance(v, str) and v.startswith('https://'):
            out.append(v)
    return out[:4]


def offer(value):
    """(price, currency, available) from offers: an Offer, a list of them, or an AggregateOffer."""
    offers = [o for o in walk(value) if kind(o) & {'offer', 'aggregateoffer'}] or \
        [o for o in walk(value) if 'price' in o or 'lowPrice' in o]
    best = None
    for o in offers:
        try:
            price = float(str(o.get('price') or o.get('lowPrice')).replace(',', ''))
        except (TypeError, ValueError):
            continue
        available = 'instock' in str(o.get('availability', 'instock')).lower().replace(' ', '') or \
            'preorder' in str(o.get('availability', '')).lower()
        candidate = (not available, price, str(o.get('priceCurrency') or '').upper(), available)
        best = min(best, candidate) if best else candidate
    return best[1:] if best else (None, None, None)


def meta(page, name):
    m = re.search(rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']*)', page, re.I) or \
        re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(name)}["\']', page, re.I)
    return html.unescape(m.group(1)).strip() if m else None


def products(page, url):
    """Products a store page describes: JSON-LD first, then Open Graph product tags (many themes have one or both)."""
    found = []
    for node in (n for doc in json_ld(page) for n in walk(doc)):
        if not kind(node) & PRODUCT_TYPES or not text(node.get('name')):
            continue
        price, currency, available = offer(node.get('offers'))
        if price is None:
            continue
        link = node.get('url') if isinstance(node.get('url'), str) and node['url'].startswith('https://') else url
        found.append({'title': text(node['name']), 'url': link, 'price': price, 'currency': currency,
                      'available': available, 'image_urls': images(node.get('image')), 'brand': text(node.get('brand')),
                      'description': re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text(node.get('description')) or ''))})
    if not found and (price := meta(page, 'product:price:amount') or meta(page, 'og:price:amount')):
        try:
            found.append({'title': meta(page, 'og:title'), 'url': url, 'price': float(price.replace(',', '')),
                          'currency': (meta(page, 'product:price:currency') or meta(page, 'og:price:currency') or '').upper(),
                          'available': 'out' not in (meta(page, 'product:availability') or '').lower(),
                          'image_urls': images(meta(page, 'og:image')), 'brand': None,
                          'description': meta(page, 'og:description') or ''})
        except ValueError:
            pass
    return [p for p in found if p['title'] and len(p['currency'] or '') == 3][:4]


def listing(product, site_name, provenance):
    url = urlunsplit((*urlsplit(product['url'])[:3], '', ''))
    shop = site_name or host(url)
    return Listing(id='web:' + hashlib.sha256(url.encode()).hexdigest()[:20], source='web', title=product['title'][:500],
        url=url, image_urls=product['image_urls'], description=product['description'][:2500], price=product['price'],
        currency=product['currency'], condition='new', available=product['available'], seller=shop, retailer=shop,
        marketplace='web', tier='small_shop', brand=product['brand'] or shop, is_ad=False, scraped_at=now(),
        provenance=provenance)


class WebShops:
    def __init__(self, settings):
        self.api_key = settings.brightdata_api_key
        self.serp_zone, self.unlocker_zone = settings.brightdata_serp_zone, settings.brightdata_unlocker_zone

    @property
    def enabled(self):
        return bool(self.serp_zone and self.unlocker_zone)

    def client(self):
        # Without a key (runs behind an injecting proxy) the header is supplied in transit.
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        return httpx.AsyncClient(base_url=API, headers=headers, timeout=60)

    async def serp(self, http, query):
        url = f'https://www.google.com/search?q={quote_plus(query)}&num=20&hl=en&gl=us&brd_json=1'
        for attempt in range(2):  # Bright Data answers an occasional 502; one retry is usually enough
            response = await http.post('request', json={'zone': self.serp_zone, 'url': url, 'format': 'raw'})
            if response.status_code < 500 or attempt:
                break
        response.raise_for_status()
        return [r for r in response.json().get('organic') or [] if isinstance(r, dict) and r.get('link')]

    async def read(self, http, url, query):
        """Products behind a search result: the page's own product data; for a Shopify store's collection page, its
        catalog's best matches; otherwise up to two product pages it links to on the same site."""
        page = await self.unlock(http, url)
        found = products(page, url)
        if found:
            return found
        site = host(url)
        if SHOPIFY.search(page):
            try:
                catalog = json.loads(await self.unlock(http, f'https://{site}/products.json?limit=250')).get('products') or []
            except ValueError:
                catalog = []
            ranked = sorted(((indie.score(query, p), p) for p in catalog if isinstance(p, dict)), key=lambda x: -x[0])
            rows = [indie.listing(p, {'domain': site, 'name': site}) for points, p in ranked[:3] if points > 0]
            return [{'title': r['title'], 'url': r['url'], 'price': r['price'], 'currency': r['currency'],
                     'available': r['available'], 'image_urls': r['image_urls'], 'brand': r['brand'],
                     'description': r['description']} for r in rows if r and r['url'] and r['price'] is not None]
        links = list(dict.fromkeys(u for u in PRODUCT_LINK.findall(page) if host(u if '://' in u else f'https://{site}{u}') == site))
        out = []
        for link in links[:2]:
            link = link if '://' in link else f'https://{site}{link}'
            try:
                out += products(await self.unlock(http, link), link)
            except (httpx.HTTPError, ValueError):
                continue
        return out

    async def unlock(self, http, url):
        response = await http.post('request', json={'zone': self.unlocker_zone, 'url': url, 'format': 'raw'})
        response.raise_for_status()
        return response.text

    async def search(self, queries, limit, max_price=None, shops=()):
        """(listings, summary) for a search's query variants. A failed page is skipped, a failed search is raised
        only when every Google search failed."""
        queries = queries if isinstance(queries, list) else [queries]
        shops = [s for s in shops if s.platform == 'web']  # Shopify shops are niche-indie's
        names = {s.domain: s.name for s in shops}
        searches = queries_for(queries[0], shops) + [q for v in queries[1:2] for q in queries_for(v)[:1]]
        async with self.client() as http:
            results = await asyncio.gather(*(self.serp(http, q) for q in searches), return_exceptions=True)
            if all(isinstance(r, BaseException) for r in results):
                raise next(r for r in results if isinstance(r, BaseException))
            pages, per_site = [], {}
            for row in (x for r in results if not isinstance(r, BaseException) for x in r):
                url, site = row['link'], host(row['link'])
                if not url.startswith('https://') or url in pages or not (site in names or independent(url)) \
                        or ARTICLE.search(urlsplit(url).path):
                    continue
                if per_site.get(site, 0) >= 3:
                    continue
                per_site[site] = per_site.get(site, 0) + 1
                pages.append(url)
            slots = asyncio.Semaphore(AT_ONCE)

            async def read(url):
                async with slots:
                    try:
                        return url, await asyncio.wait_for(self.read(http, url, queries[0]), PAGE_SECONDS)
                    except (httpx.HTTPError, ValueError, TimeoutError):
                        return url, None
            read_pages = await asyncio.gather(*(read(u) for u in pages[:MAX_PAGES]))
        provenance = {'provider': 'brightdata', 'serp_zone': self.serp_zone}
        listings, seen = [], set()
        for url, found in read_pages:
            for product in found or []:
                item = listing(product, names.get(host(url)), {**provenance, 'page': url})
                if item.url in seen or not item.available or (max_price and item.price > max_price):
                    continue
                seen.add(item.url)
                listings.append(item)
        return listings[:limit], {'status': 'succeeded', 'count': len(listings[:limit]), 'searches': len(searches),
            'pages': len(read_pages), 'pages_with_products': sum(bool(f) for _, f in read_pages)}
