import asyncio
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app import create_app
from sourcing.config import Settings
from sourcing.models import IndieShop, SearchRequest
from sourcing.sources import ApifySources, INDIE_SHOPS
from sourcing.store import Store
from taste import brands, shops

BATUL = IndieShop(domain='batulthecollection.com', name='Batul The Collection')


def test_domain_and_name_guesses():
    assert shops.domain_of('https://www.BatulTheCollection.com/collections/new') == 'batulthecollection.com'
    assert shops.domain_of('velathelabel.com') == 'velathelabel.com'
    assert shops.domain_of('Batul The Collection') is None
    guessed = shops.guesses('Batul The Collection')
    assert guessed[:2] == ['batulthecollection.com', 'batulthecollection.co'] and 'batul.com' in guessed
    assert 'velathelabel.com' in shops.guesses('Vela') and 'shopveiled.com' in shops.guesses('Veiled')


def fake_web(monkeypatch, sites):
    """sites: domain -> store name for the Shopify stores that answer; everything else fails like a missing site."""
    async def read_json(http, url):
        domain, path = url.removeprefix('https://').split('/', 1)
        if domain not in sites:
            return None
        return {'products': [{'id': 1}]} if path.startswith('products.json') else {'name': sites[domain], 'currency': 'usd'}
    monkeypatch.setattr(shops, 'read_json', read_json)


def test_find_by_name_only_trusts_a_store_with_that_name(monkeypatch):
    # vela.com is someone else's Shopify store; velathelabel.com calls itself Vela.
    fake_web(monkeypatch, {'vela.com': 'Candle Supply Co', 'velathelabel.com': 'VELA'})
    found = asyncio.run(shops.find('Vela', http=object()))
    assert found == IndieShop(domain='velathelabel.com', name='VELA', currency='USD')
    assert asyncio.run(shops.find('Nobody', http=object())) is None


def test_find_by_website_takes_the_store_as_given(monkeypatch):
    fake_web(monkeypatch, {'www.veiled.shop': 'Veiled Studio'})
    assert asyncio.run(shops.find('https://veiled.shop/products/x', http=object())).domain == 'www.veiled.shop'


def test_indie_actor_gets_the_shoppers_shops_first_then_the_seed_list(tmp_path):
    sources = ApifySources(Settings(), Store(str(tmp_path/'s.sqlite')))
    _, plain = sources.actor_input('indie', ['satin dress'], 30)
    assert 'shops' not in plain  # the actor uses its own seed list
    _, mine = sources.actor_input('indie', ['satin dress'], 30, shops=[BATUL, IndieShop(**INDIE_SHOPS[0])])
    _, new = sources.actor_input('indie', ['satin dress'], 30, shops=[IndieShop(domain='newlabel.example', name='New')])
    assert len(new['shops']) == len(INDIE_SHOPS) + 1 and new['shops'][0]['domain'] == 'newlabel.example'
    domains = [s['domain'] for s in mine['shops']]
    assert domains[0] == 'batulthecollection.com' and len(domains) == len(set(domains))
    assert set(domains) == {s['domain'] for s in INDIE_SHOPS}  # Batul is in the seed list too, sent once
    _, other = sources.actor_input('secondhand', ['satin dress'], 30, shops=[BATUL])
    assert 'shops' not in other


def test_pipeline_passes_shops_to_indie_only(tmp_path):
    from sourcing.pipeline import Pipeline
    from sourcing.sources import FixtureSources
    calls = {}

    class Recording(FixtureSources):
        async def fetch(self, source, query, limit, job_id, max_price=None, **named):
            calls[source] = named.get('shops')
            return await super().fetch(source, query, limit, job_id, max_price)

    data = json.loads(Path('examples/search.json').read_text())
    data['taste_profile']['indie_shops'] = [BATUL.model_dump()]
    data['sources'] = ['indie', 'mainstream']
    store = Store(str(tmp_path/'p.sqlite'))
    request = SearchRequest.model_validate(data)
    job = store.create(request.model_dump(mode='json'))
    asyncio.run(Pipeline(Settings(), store, sources=Recording()).run(request, job))
    assert calls == {'indie': [BATUL], 'mainstream': None}


@pytest.fixture
def client(tmp_path, monkeypatch):
    async def verify(shop, http=None):
        return shop  # checks are covered in test_brands.py
    monkeypatch.setattr(brands, 'verify', verify)
    settings = Settings(database_path=str(tmp_path/'api.sqlite'), upload_dir=str(tmp_path/'uploads'))
    with TestClient(create_app(settings)) as client:
        yield client


def test_add_and_remove_a_shop(client, monkeypatch):
    async def find(text, http=None, any_platform=False):
        return BATUL if 'batul' in text.lower() else None
    monkeypatch.setattr(shops, 'find', find)
    pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    added = client.post(f'/v1/taste/profiles/{pid}/shops', json={'shop': 'Batul The Collection'})
    assert added.status_code == 201 and added.json()['profile']['indie_shops'] == [BATUL.model_dump()]
    again = client.post(f'/v1/taste/profiles/{pid}/shops', json={'shop': 'batulthecollection.com'}).json()
    assert len(again['profile']['indie_shops']) == 1
    # A brand without a shop Niche can read (most big brands) is kept as a favorite instead of refused.
    missing = client.post(f'/v1/taste/profiles/{pid}/shops', json={'shop': 'Unknown Label'}).json()
    assert len(missing['profile']['indie_shops']) == 1 and 'Unknown Label' in missing['profile']['onboarding']['favorite_brands']
    again = client.post(f'/v1/taste/profiles/{pid}/shops', json={'shop': 'unknown label'}).json()
    assert again['profile']['onboarding']['favorite_brands'].count('Unknown Label') == 1
    removed = client.delete(f'/v1/taste/profiles/{pid}/shops/batulthecollection.com').json()
    assert removed['profile']['indie_shops'] == []


def test_build_looks_up_favorite_brands_once(client, monkeypatch):
    looked_up = []

    async def find_many(names, timeout=15):
        looked_up.append(list(names))
        return [BATUL] if 'Batul The Collection' in names else []
    monkeypatch.setattr(shops, 'find_many', find_many)
    pid = client.post('/v1/taste/profiles', json={'data_consent': True, 'favorite_brands': ['Batul The Collection', 'Vela']}).json()['profile']['id']
    client.put(f'/v1/taste/profiles/{pid}/notes', json={'notes': ['long black satin skirts']})
    built = client.post(f'/v1/taste/profiles/{pid}/build').json()['profile']
    assert built['indie_shops'] == [BATUL.model_dump()] and looked_up == [['Batul The Collection', 'Vela']]
    client.post(f'/v1/taste/profiles/{pid}/build')
    assert len(looked_up) == 1  # nothing new to look up
