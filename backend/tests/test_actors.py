import asyncio
import json

import httpx
import pytest

from niche_actors import core, normalize, retailers


def test_retailer_bank_matches_google_store_names():
    assert retailers.lookup('Zara USA') == ('Zara', 'fast_fashion')
    assert retailers.lookup('Nordstrom Rack') == ('Nordstrom Rack', 'off_price')
    assert retailers.lookup("KOHL'S") == ("Kohl's", 'department')
    assert retailers.lookup('Abercrombie and Fitch') == ('Abercrombie & Fitch', 'mainstream')
    assert retailers.lookup('Some Boutique') is None
    assert retailers.lookup(None) is None
    assert {tier for _, tier, _ in retailers.RETAILERS} <= set(retailers.TIERS)


def google_row(store='Gap', price='$158.00'):
    return {'product_id': 'catalogid:1', 'product_title': 'Wool-Blend Peacoat', 'price': price, 'store_name': store,
            'product_page_url': 'https://www.google.com/search?ibp=oshop&prds=catalogid:1',
            'product_photos': ['https://encrypted-tbn0.gstatic.com/shopping?q=1'], 'shipping': 'Free delivery'}


def test_google_shopping_keeps_only_bank_stores():
    row = normalize.google_shopping(google_row())
    assert row['retailer'] == 'Gap' and row['tier'] == 'mainstream' and row['price'] == 158.0
    assert row['condition'] == 'new' and row['image_urls'] and row['id'] == 'google_shopping:catalogid:1'
    assert normalize.google_shopping(google_row('Some Boutique')) is None
    assert normalize.google_shopping(google_row('Some Boutique'), include_unlisted=True)['tier'] == 'small_shop'
    assert normalize.google_shopping(google_row(price='call for price')) is None


def test_resale_parsers_drop_sold_and_flag_promoted():
    depop = {'id': 1, 'url': 'https://www.depop.com/products/x/', 'title': 'Wool coat', 'price': 35, 'currency': 'USD',
             'isOnSale': True, 'isBoosted': True, 'sizes': [{'name': 'L'}], 'pictures': ['https://media-photos.depop.com/1.jpg'],
             'brandName': 'Pendleton', 'shippingCost': 5.99}
    row = normalize.depop(depop)
    assert row['is_ad'] and row['sizes'] == ['L'] and row['brand'] == 'Pendleton' and row['tier'] == 'resale'
    assert normalize.depop({**depop, 'isSold': True}) is None
    assert normalize.depop({**depop, 'url': 'https://evil.example/products/x/'}) is None

    posh = {'link': 'https://poshmark.com/listing/Wool-Coat-6adc', 'image': 'https://di2ponv0v5otw.cloudfront.net/1.jpg',
            'title': 'Wool Coat', 'priceValue': 90, 'currency': 'USD', 'size': 'S', 'isSold': False}
    assert normalize.poshmark(posh)['id'] == 'poshmark:6adc'
    assert normalize.poshmark({**posh, 'isSold': True}) is None

    vinted = {'id': 7, 'title': 'Brown wool coat', 'price': {'amount': '20.00', 'currency_code': 'USD'},
              'url': 'https://www.vinted.com/items/7-brown-wool-coat', 'photo': {'url': 'https://images1.vinted.net/1.webp'},
              'size_title': 'M', 'status': 'Very good', 'brand_title': 'Ralph Lauren', 'promoted': False,
              'user': {'login': 'seller'}}
    row = normalize.vinted(vinted)
    assert row['price'] == 20.0 and row['condition'] == 'Very good' and row['seller'] == 'seller' and not row['is_ad']


def test_clean_drops_ads_over_budget_and_duplicates():
    base = normalize.google_shopping(google_row())
    rows = [base, dict(base), {**base, 'id': 'x', 'is_ad': True}, {**base, 'id': 'y', 'url': 'https://a.example/y', 'price': 500}]
    assert core.clean(rows, max_price=200) == [base]


def test_collect_isolates_failures_and_retries_concurrency_limit(monkeypatch):
    calls = {'starts': 0}
    depop_row = {'id': 1, 'url': 'https://www.depop.com/products/x/', 'title': 'Wool coat', 'price': 35,
                 'currency': 'USD', 'isOnSale': True}

    def handler(request):
        path = request.url.path
        if path.endswith('/runs') and 'depop' in path:
            calls['starts'] += 1
            if calls['starts'] == 1:  # first start refused by the plan's concurrent-run limit
                return httpx.Response(402, json={'error': {'type': 'concurrent-runs-limit-exceeded',
                                                           'message': 'exceed your limit of 5 concurrent Actor runs'}})
            return httpx.Response(201, json={'data': {'id': 'r1', 'status': 'SUCCEEDED', 'defaultDatasetId': 'd1'}})
        if path.endswith('/runs'):
            return httpx.Response(400, json={'error': {'type': 'invalid-input', 'message': 'bad input'}})
        if path.endswith('/datasets/d1/items'):
            return httpx.Response(200, json=[depop_row, {**depop_row, 'id': 2, 'isSold': True}])
        raise AssertionError(path)

    real_sleep = asyncio.sleep
    monkeypatch.setattr(core, 'client', lambda: httpx.AsyncClient(base_url=core.API, transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(core.asyncio, 'sleep', lambda *_: real_sleep(0))
    rows, sources = asyncio.run(core.collect(['depop', 'vinted'], ['wool coat'], items_per_query=5, max_price=100))
    assert calls['starts'] == 2
    assert [r['id'] for r in rows] == ['depop:1']
    assert sources['depop'] == {'status': 'succeeded', 'received': 2, 'kept': 1, 'actor': 'abotapi/depop-scraper'}
    assert sources['vinted']['status'] == 'failed' and sources['vinted']['type'] == 'invalid-input'


def test_scraper_inputs_respect_minimums_and_budget():
    google = core.SCRAPERS['google_shopping'].build(['a', 'b'], 3, 120)
    assert [p['limit'] for p in google] == [10, 10] and google[0]['maxPrice'] == 120
    etsy = core.SCRAPERS['etsy'].build(['a'], 3, None)[0]
    assert etsy['maxItems'] == 10 and 'maxPrice' not in etsy
    posh = core.SCRAPERS['poshmark'].build(['wool coat'], 4, None)[0]
    assert posh['searchUrls'] == ['https://poshmark.com/search?query=wool%20coat&availability=available']


def test_actor_specs_are_valid_for_apify():
    for mode in ('mainstream', 'secondhand'):
        with open(f'actors/{mode}/.actor/actor.json') as f:
            spec = json.load(f)
        assert spec['name'] == f'niche-{mode}'
        # Apify rejects a build when any input property lacks a description.
        assert all(p.get('description') for p in spec['input']['properties'].values())


@pytest.mark.parametrize('mode', ['mainstream', 'secondhand'])
def test_handlers_run_offline(mode, monkeypatch):
    from niche_actors import mainstream, secondhand
    handler = {'mainstream': mainstream, 'secondhand': secondhand}[mode].handle

    async def fake_collect(marketplaces, queries, *args, **kwargs):
        return [normalize.google_shopping(google_row())], {m: {'status': 'succeeded'} for m in marketplaces}

    monkeypatch.setattr(f'niche_actors.{mode}.collect', fake_collect)
    rows, summary = asyncio.run(handler({'queries': ['coat'], 'tiers': ['department']}))
    assert summary['actor'] == f'niche-{mode}'
    if mode == 'mainstream':
        assert rows == []  # Gap is mainstream, filtered out by tiers=['department']
    else:
        assert set(summary['sources']) == {'depop', 'poshmark', 'vinted', 'etsy'}
