"""niche-secondhand: active listings from resale marketplaces and small shops, one labelled list.

Input: {"queries": ["vintage wool coat"], "maxPrice": 120, "itemsPerQuery": 10,
        "marketplaces": ["depop", "poshmark", "vinted", "etsy"]}
Grailed is opt-in because its scraper charges $0.20 per run.
"""
from .core import collect
from .platform import run

DEFAULT = ['depop', 'poshmark', 'vinted', 'etsy']
ALLOWED = {*DEFAULT, 'grailed'}


async def handle(data):
    marketplaces = [m for m in data.get('marketplaces') or DEFAULT if m in ALLOWED]
    rows, sources = await collect(marketplaces, data.get('queries') or [], data.get('itemsPerQuery', 10),
                                  data.get('maxPrice'), max_concurrent_runs=data.get('maxConcurrentRuns', 2))
    return rows, {'actor': 'niche-secondhand', 'sources': sources, 'count': len(rows)}


if __name__ == '__main__':
    run(handle)
