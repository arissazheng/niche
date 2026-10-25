import asyncio
from fastapi.testclient import TestClient
from app import create_app
from sourcing.config import Settings
from sourcing.models import IndieShop
from sourcing.store import Store
from taste import brands, labels as labels_module, shops
from taste.labels import INDEX, Labels
from tests.test_finds import moss, wait_for  # noqa: F401  (fixture)

BATUL = IndieShop(domain='batulthecollection.com', name='Batul The Collection')
OTHER = IndieShop(domain='other.example', name='Other Label')


def product(i, title, price='150.00', available=True):
    return {'id': i, 'title': title, 'handle': f'p{i}', 'vendor': 'Batul', 'product_type': 'Skirt', 'tags': 'satin',
            'variants': [{'price': price, 'available': available}], 'images': [{'src': f'https://cdn.x/{i}.jpg'}]}


CATALOGS = {BATUL.domain: [product(1, 'Silk slip skirt'), product(2, 'Wool coat', available=False)],
            OTHER.domain: [product(3, 'Silk slip skirt in ivory')]}


async def fake_catalog(http, domain):
    return CATALOGS[domain]


def settings(tmp_path):
    return Settings(database_path=str(tmp_path/'l.sqlite'), upload_dir=str(tmp_path/'up'),
                    moss_project_id='moss-project', moss_project_key='moss-key')


def test_catalogs_are_indexed_and_recalled_only_for_the_shoppers_labels(tmp_path, moss, monkeypatch):
    monkeypatch.setattr(labels_module, 'catalog', fake_catalog)
    s = settings(tmp_path)
    labels = Labels(s, Store(s.database_path))

    async def run():
        await labels.index(BATUL)
        await labels.index(OTHER)
        return (await labels.recall_labels([BATUL], 'silk slip skirt'),
                await labels.recall_labels([BATUL], 'silk slip skirt', max_price=100))
    mine, capped = asyncio.run(run())
    assert set(moss.indexes[INDEX]) == {'shopify:batulthecollection.com:1', 'shopify:other.example:3'}  # sold-out coat left out
    assert [(x['title'], x['store'], x['price']) for x in mine] == [('Silk slip skirt', 'Batul The Collection', 150.0)]
    assert mine[0]['url'] == 'https://batulthecollection.com/products/p1' and capped == []


def test_adding_a_shop_indexes_its_catalog(tmp_path, moss, monkeypatch):
    async def find(text, http=None, any_platform=False):
        return BATUL

    async def verify(shop, http=None):
        return shop
    monkeypatch.setattr(shops, 'find', find)
    monkeypatch.setattr(brands, 'verify', verify)
    monkeypatch.setattr(labels_module, 'catalog', fake_catalog)
    with TestClient(create_app(settings(tmp_path))) as client:
        pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
        assert client.post(f'/v1/taste/profiles/{pid}/shops', json={'shop': 'Batul'}).status_code == 201
        assert wait_for(lambda: 'shopify:batulthecollection.com:1' in moss.indexes.get(INDEX, {}))
