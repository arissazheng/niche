"""A shopper's own independent shops: a brand name or website in, a Shopify store niche-indie can read out.

Most small labels sell from Shopify, whose stores answer https://<shop>/products.json and /meta.json publicly. A
website is checked as given; a bare name is tried against the domains small labels usually pick (batul.com,
velathelabel.com, shopveiled.com...). A guessed domain only counts when the store calls itself by that name, so a
stranger's shop that happens to own the domain isn't added. A website on another platform is kept as a `web` shop
when Bright Data is set up (sourcing/webshops.py reads those through Google and the Web Unlocker).
"""
import asyncio
import html
import json
import re
from sourcing import safe_fetch
from sourcing.models import IndieShop

from actors.niche_actors.labels import FILLER, domain_of, guesses, slug  # shared with the independent-labels actor

MAX_BYTES = 2_000_000


async def read_json(http, url):
    got = await safe_fetch.fetch(http, url, MAX_BYTES)
    if not got:
        return None
    try:
        return json.loads(got[0])
    except ValueError:
        return None


async def check(http, domain, name=None):
    """The shop at this domain, when it's a Shopify store selling something (and, for a guess, calls itself name)."""
    catalog = await read_json(http, f'https://{domain}/products.json?limit=1')
    if not isinstance(catalog, dict) or not catalog.get('products'):
        return None
    meta = await read_json(http, f'https://{domain}/meta.json') or {}
    title = str(meta.get('name') or '').strip()[:80] if isinstance(meta, dict) else ''
    if name and slug(FILLER.sub(' ', name.lower())) not in slug(title or ''):
        return None
    currency = str(meta.get('currency') or 'USD').upper() if isinstance(meta, dict) else 'USD'
    return IndieShop(domain=domain, name=title or name or domain,
                     currency=currency if re.fullmatch(r'[A-Z]{3}', currency) else 'USD')


async def site_name(http, domain):
    """A store's own name from its homepage (og:site_name or <title>), else its domain."""
    got = await safe_fetch.fetch(http, f'https://{domain}/', MAX_BYTES)
    page = got[0].decode('utf-8', 'replace') if got else ''
    m = re.search(r'property=["\']og:site_name["\'][^>]+content=["\']([^"\']+)', page) or \
        re.search(r'<title[^>]*>([^<|–-]+)', page, re.I)
    return html.unescape(m.group(1)).strip()[:80] if m and m.group(1).strip() else domain


async def find(text, http=None, any_platform=False):
    """A brand name or website -> its IndieShop, or None when no store for it can be read. A website on another
    platform than Shopify is kept as a `web` shop when any_platform (Bright Data is set up to read those)."""
    own = http is None
    http = http or safe_fetch.client()
    try:
        domain = domain_of(text)
        if domain:
            shop = await check(http, domain) or await check(http, 'www.' + domain)
            if shop or not any_platform:
                return shop
            return IndieShop(domain=domain, name=await site_name(http, domain), platform='web')
        found = await asyncio.gather(*(check(http, d, text) for d in guesses(text)))
        return next((shop for shop in found if shop), None)
    finally:
        if own:
            await http.aclose()


async def find_many(names, timeout=15):
    """Look up several brand names at once (best effort: a slow or missing shop is just skipped)."""
    async def one(http, name):
        try:
            return await asyncio.wait_for(find(name, http), timeout)
        except TimeoutError:
            return None

    async with safe_fetch.client() as http:
        return [shop for shop in await asyncio.gather(*(one(http, n) for n in names)) if shop]
