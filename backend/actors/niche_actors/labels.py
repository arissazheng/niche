"""independent-labels: verified independent fashion labels and their in-stock products, from brand names or websites.

Give it brands ("Batul The Collection", "velathelabel.com") and, optionally, what you're looking for. For each brand it
finds the label's own Shopify store (a website as given; a name against the domains small labels usually pick, kept
only when the store calls itself by that name), checks that it is a real independent label, and returns its in-stock
products, best matches first. Everything comes from each store's public /products.json and /meta.json: no
third-party scrapers, no logins.

Checks (a brand is verified when all pass):
  real_store   sells something with a price, in stock
  independent  not a marketplace, chain or big retailer
  own_label    one label's store, not a boutique or reseller of many brands (few vendors, or one with most products)
  small        under SMALL_CATALOG products
  established  selling for over ESTABLISHED_DAYS days (drop-shipping stores rarely are)

Input: {"brands": ["Batul The Collection", "velathelabel.com"], "query": "slip skirt", "maxPrice": 250,
        "itemsPerBrand": 10, "verifiedOnly": true}
Niche's backend uses the same resolution and checks (backend/taste/shops.py, backend/taste/brands.py).
"""
import asyncio
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx

from . import indie, retailers

SMALL_CATALOG = 1000
ESTABLISHED_DAYS = 180
MAX_VENDORS = 9  # labels list makers and partner workshops as vendors too; boutiques carry many more brands
OWN_SHARE = 0.5  # or most products under one vendor name
PAGES = 4
CHECKS = ('real_store', 'independent', 'own_label', 'small', 'established')
# Words labels add to a domain or drop from it: "Batul The Collection" -> batul, batulthecollection, ...
FILLER = re.compile(r'\b(the|collection|label|studio|official|shop|store|clothing|brand)\b')
SUFFIXES = ('thelabel', 'thecollection', 'label', 'studio', 'clothing', 'official')
PREFIXES = ('shop', 'the', 'wear')
# Not independent labels: marketplaces, big retailers' own domains, social sites and press. Retailer-bank names are
# checked too (retailers.py), so nordstrom.com or zara.com never count as small shops.
NOT_INDIE = re.compile(r'(^|\.)(amazon|ebay|etsy|depop|poshmark|grailed|vinted|mercari|therealreal|vestiairecollective|'
    r'shein|temu|aliexpress|alibaba|walmart|target|asos|revolve|farfetch|ssense|net-a-porter|mytheresa|shopbop|'
    r'nordstrom|nordstromrack|saksfifthavenue|neimanmarcus|bloomingdales|macys|zara|hm|uniqlo|urbanoutfitters|'
    r'anthropologie|freepeople|abercrombie|lulus|princesspolly|fashionnova|boohoo|prettylittlething|lyst|shopstyle|'
    r'pinterest|instagram|facebook|tiktok|youtube|reddit|twitter|x|wikipedia|vogue|elle|harpersbazaar|whowhatwear|'
    r'refinery29|cosmopolitan|nytimes|buzzfeed|google|shopmy|ltk|liketoknow|substack|medium|tumblr|lululemon)\.[a-z.]+$')


def slug(text):
    return re.sub(r'[^a-z0-9]', '', text.lower())


def base_name(name):
    return slug(FILLER.sub(' ', name.lower())) or slug(name)


def domain_of(text):
    """'https://www.Batul.com/collections/x' -> 'batul.com'; None when it isn't a website."""
    text = text.strip()
    if not re.search(r'\.[a-z]{2,}(/|$)', text.lower()):
        return None
    host = (urlsplit(text if '://' in text else f'https://{text}').hostname or '').lower()
    host = host[4:] if host.startswith('www.') else host
    return host if re.fullmatch(r'[a-z0-9-]+(\.[a-z0-9-]+)+', host) else None


def guesses(name):
    """Likely shop domains for a brand name, most likely first."""
    full, base = slug(name), base_name(name)
    names = list(dict.fromkeys([full, base] + [base + s for s in SUFFIXES] + [p + base for p in PREFIXES]))
    return [f'{n}.{tld}' for n in names if 2 < len(n) <= 40 for tld in ('com', 'co')][:24]


def host(url):
    h = (urlsplit(url).hostname or '').lower()
    return h[4:] if h.startswith('www.') else h


def independent(url):
    h = host(url)
    if not h or NOT_INDIE.search(h):
        return False
    stem = retailers.key(h.rsplit('.', 1)[0].replace('shop', '').replace('store', ''))
    return stem not in retailers.INDEX


def checks(domain, products, today=None):
    today = today or datetime.now(timezone.utc)
    variants = [v for p in products for v in p.get('variants') or [] if isinstance(v, dict)]
    vendors = {vendor(p) for p in products} - {''}
    dates = []
    for p in products:
        try:
            dates.append(datetime.fromisoformat(str(p.get('published_at') or p.get('created_at'))))
        except ValueError:
            continue
    return {'real_store': any(v.get('available') and v.get('price') for v in variants),
            'independent': independent(f'https://{domain}/'),
            'own_label': bool(products) and (len(vendors) <= MAX_VENDORS or main_share(products) >= OWN_SHARE),
            'small': bool(products) and len(products) < SMALL_CATALOG,
            'established': bool(dates) and (today - min(dates)).days >= ESTABLISHED_DAYS}


def vendor(product):
    # Some labels put season codes in `vendor` ("F26A", "PF25"); those aren't other brands.
    name = str(product.get('vendor') or '').strip().lower()
    return '' if re.search(r'\d', name) else name


def main_share(products):
    counts = {}
    for p in products:
        counts[vendor(p)] = counts.get(vendor(p), 0) + 1
    counts.pop('', None)
    return max(counts.values()) / sum(counts.values()) if counts else 1


async def get_json(http, url):
    try:
        response = await http.get(url)
        return response.json() if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        return None


async def store(http, domain, name=None):
    """{domain, name, currency} when a Shopify store answers there (and, for a guess, calls itself name)."""
    first = await get_json(http, f'https://{domain}/products.json?limit=1')
    if not isinstance(first, dict) or not first.get('products'):
        return None
    meta = await get_json(http, f'https://{domain}/meta.json') or {}
    title = str(meta.get('name') or '').strip()[:80] if isinstance(meta, dict) else ''
    if name and base_name(name) not in slug(title):
        return None
    currency = str((meta.get('currency') if isinstance(meta, dict) else None) or 'USD').upper()
    return {'domain': domain, 'name': title or name or domain, 'currency': currency if len(currency) == 3 else 'USD'}


async def resolve(http, text):
    domain = domain_of(text)
    if domain:
        return await store(http, domain) or await store(http, 'www.' + domain)
    found = await asyncio.gather(*(store(http, d, text) for d in guesses(text)))
    return next((s for s in found if s), None)


async def products_of(http, domain):
    products = []
    for page in range(1, PAGES + 1):
        batch = (await get_json(http, f'https://{domain}/products.json?limit=250&page={page}') or {}).get('products') or []
        products += [p for p in batch if isinstance(p, dict)]
        if len(batch) < 250:
            break
    return products


async def handle(data, push=None):
    brands = [b.strip() for b in data.get('brands') or [] if isinstance(b, str) and b.strip()][:50]
    query, cap = (data.get('query') or '').strip(), data.get('maxPrice')
    per_brand, verified_only = data.get('itemsPerBrand', 10), data.get('verifiedOnly', True)
    slots, sources, rows = asyncio.Semaphore(indie.AT_ONCE), {}, []

    async def one(http, text):
        async with slots:
            shop = await resolve(http, text)
            if not shop:
                sources[text] = {'status': 'failed', 'error': 'no Shopify store found; try the brand website'}
                return
            products = await products_of(http, shop['domain'])
        result = checks(shop['domain'], products)
        verified = all(result.values())
        names = {}
        for p in products:
            names[vendor(p)] = names.get(vendor(p), 0) + 1
        names.pop('', None)
        sources[text] = {'status': 'succeeded', **shop, 'verified': verified, 'checks': result,
                         'products': len(products), 'vendors': dict(sorted(names.items(), key=lambda x: -x[1])[:5])}
        if verified_only and not verified:
            return
        found = []
        for product in products:
            row = indie.listing(product, shop)
            if not row or not row['available'] or (cap and row['price'] > cap):
                continue
            points = indie.score(query, product) if query else 1
            if points > 0:
                found.append((points, {**row, 'domain': shop['domain'], 'verified': verified, 'checks': result}))
        found.sort(key=lambda x: -x[0])
        batch = [r for _, r in found[:per_brand]]
        rows.extend(batch)
        if push and batch:
            await push(batch)

    async with indie.client() as http:
        await asyncio.gather(*(one(http, b) for b in brands))
    return rows, {'actor': 'independent-labels', 'sources': sources, 'count': len(rows),
                  'verified': sum(bool(s.get('verified')) for s in sources.values())}


if __name__ == '__main__':
    from .platform import run
    run(handle)
