"""niche-mainstream: Google Shopping results from stores in the retailer bank, one labelled list.

Input: {"queries": ["womens wool coat"], "maxPrice": 200, "itemsPerQuery": 20,
        "tiers": ["department", "mainstream"], "includeUnlisted": false}
"""
from .core import collect
from .platform import run


async def handle(data, push=None):
    rows, sources = await collect(['google_shopping'], data.get('queries') or [], data.get('itemsPerQuery', 20),
        data.get('maxPrice'), parse_options={'google_shopping': {'include_unlisted': bool(data.get('includeUnlisted'))}},
        max_concurrent_runs=data.get('maxConcurrentRuns', 2))
    if data.get('tiers'):
        rows = [r for r in rows if r['tier'] in data['tiers']]
    return rows, {'actor': 'niche-mainstream', 'sources': sources, 'count': len(rows)}


if __name__ == '__main__':
    run(handle)
