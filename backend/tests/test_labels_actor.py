import asyncio
from actors.niche_actors import labels

OLD = '2024-01-05T09:00:00-08:00'


def product(i, title, product_type='Skirts', vendor='Vela', available=True, price='140.00'):
    return {'id': i, 'title': title, 'handle': f'p{i}', 'product_type': product_type, 'vendor': vendor,
            'published_at': OLD, 'tags': '', 'variants': [{'price': price, 'available': available}]}


SITES = {  # domain -> (meta.json name, catalog)
    'velathelabel.com': ('VELA', [product(1, 'Satin slip skirt'), product(2, 'Linen shirt', 'Tops')]),
    'vela.com': ('Candle Supply Co', [product(9, 'Candle', 'Home')]),
    'resale.example': ('Resale Boutique', [product(i, f'Skirt {i}', vendor=f'Brand {"ABCDEFGHIJKL"[i]}') for i in range(12)]),
}


def fake_get_json(monkeypatch):
    async def get_json(http, url):
        domain, path = url.removeprefix('https://').split('/', 1)
        if domain not in SITES:
            return None
        name, products = SITES[domain]
        if path.startswith('meta.json'):
            return {'name': name, 'currency': 'USD'}
        return {'products': products[:1] if 'limit=1&' in path + '&' else products}
    monkeypatch.setattr(labels, 'get_json', get_json)


def test_finds_verifies_and_matches_each_brand(monkeypatch):
    fake_get_json(monkeypatch)
    rows, summary = asyncio.run(labels.handle({'brands': ['Vela', 'resale.example', 'Nobody'], 'query': 'slip skirt'}))
    assert [(r['title'], r['domain'], r['verified']) for r in rows] == [('Satin slip skirt', 'velathelabel.com', True)]
    s = summary['sources']
    assert s['Vela']['domain'] == 'velathelabel.com' and s['Vela']['verified']  # not the candle shop at vela.com
    assert s['resale.example']['verified'] is False and not s['resale.example']['checks']['own_label']
    assert s['Nobody']['status'] == 'failed' and summary['verified'] == 1


def test_unverified_labels_can_be_included(monkeypatch):
    fake_get_json(monkeypatch)
    rows, _ = asyncio.run(labels.handle({'brands': ['resale.example'], 'verifiedOnly': False, 'itemsPerBrand': 2}))
    assert len(rows) == 2 and not rows[0]['verified']


def test_season_codes_in_vendor_are_not_other_brands():
    codes = [product(i, f'Dress {i}', 'Dresses', vendor=v) for i, v in enumerate(['F26A', 'H26', 'F26B', 'PF26', 'F25'])]
    assert labels.checks('christydawn.com', codes)['own_label']
