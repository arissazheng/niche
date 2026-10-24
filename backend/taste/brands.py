"""Verified independent labels: the checks a shop passes before Niche calls it independent, and brand discovery.

Checks read the store's public Shopify catalog (/products.json), so they cost nothing and run in a second or two;
they live in backend/actors/niche_actors/labels.py, shared with the public independent-labels actor (real store,
independent, own label, small catalog, established). A shop is verified when every check passes. Stores on other platforms can't be checked this way yet (None).

Discovery: Claude names independent labels close to the shopper's taste and favorite brands, with each one's website;
only those whose site is a real store that passes every check are shown. Claude's names are never shown unverified.
"""
import asyncio
import json
from pydantic import BaseModel, Field
from sourcing import safe_fetch
from sourcing.models import IndieShop
from actors.niche_actors.labels import CHECKS, checks as label_checks  # shared with the actor
from . import shops

PAGES = 4  # 250 products a page: enough to tell a small catalog from a big one
SUGGESTIONS = 12


class Suggestion(BaseModel):
    name: str = Field(max_length=80)
    website: str = Field(max_length=200)
    reason: str = Field(max_length=300)


class Suggestions(BaseModel):
    brands: list[Suggestion] = Field(max_length=SUGGESTIONS)


DISCOVER = f"""You suggest small independent fashion labels a shopper would like. Input is JSON: the shopper's taste
summary, colors, silhouettes and materials, the labels they already love, and labels to leave out.
Suggest up to {SUGGESTIONS} real, currently operating independent labels that sell from their own website: designer-run
or small-team brands, not department stores, chains, marketplaces, fast fashion or big brands. Prefer labels close to
the ones the shopper loves and to their taste. Give each one's own shop website as you know it (domain only, e.g.
example.com); never guess or invent a label or a website, leave a label out if unsure. Every suggestion is checked
against the live website before a shopper sees it. reason is one short sentence on why it fits this shopper, in plain
words."""


async def catalog(http, domain):
    products = []
    for page in range(1, PAGES + 1):
        got = await safe_fetch.fetch(http, f'https://{domain}/products.json?limit=250&page={page}', 8_000_000)
        try:
            batch = json.loads(got[0]).get('products') or [] if got else []
        except (ValueError, AttributeError):
            batch = []
        products += [p for p in batch if isinstance(p, dict)]
        if len(batch) < 250:
            break
    return products


def checks(shop: IndieShop, products, today=None):
    if shop.platform != 'shopify':
        return {k: None for k in CHECKS}
    return label_checks(shop.domain, products, today)


async def verify(shop: IndieShop, http=None):
    """The shop with `verified` and `checks` filled in."""
    own = http is None
    http = http or safe_fetch.client()
    try:
        results = checks(shop, await catalog(http, shop.domain) if shop.platform == 'shopify' else [])
    finally:
        if own:
            await http.aclose()
    verified = all(results.values()) if None not in results.values() else None
    return shop.model_copy(update={'checks': results, 'verified': verified})


async def discover(model, profile, job_id, http=None):
    """[(verified IndieShop, reason)] for labels Claude suggests; unverifiable or failing ones are dropped."""
    have = {s.domain for s in profile.indie_shops}
    content = json.dumps({'taste': profile.prompt or profile.summary, 'colors': profile.colors,
        'silhouettes': profile.silhouettes, 'materials': profile.materials,
        'loves': list(dict.fromkeys(profile.onboarding.favorite_brands + [s.name for s in profile.indie_shops]
                                    + profile.designers)),
        'leave_out': profile.avoid})
    suggested = Suggestions.model_validate(
        await model.call(DISCOVER, content, job_id, 'discover_brands', 3000, Suggestions.model_json_schema(), effort='low'))
    return await verified_only([(s.website, s.reason) for s in suggested.brands], have, http)


async def verified_only(candidates, have=(), http=None):
    own = http is None
    http = http or safe_fetch.client()

    async def one(website, reason):
        try:
            shop = await asyncio.wait_for(shops.find(website, http), 15)
            if not shop or shop.domain in have:
                return None
            shop = await asyncio.wait_for(verify(shop, http), 20)
        except TimeoutError:
            return None
        return (shop, reason) if shop.verified else None
    try:
        found = await asyncio.gather(*(one(w, r) for w, r in candidates))
    finally:
        if own:
            await http.aclose()
    seen, out = set(), []
    for item in found:
        if item and item[0].domain not in seen:
            seen.add(item[0].domain)
            out.append(item)
    return out
