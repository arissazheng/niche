import json
import asyncio
from sourcing import webshops
from sourcing.config import Settings
from sourcing.models import IndieShop
from sourcing.store import Store

SQUARESPACE = '''<html><head><meta property="og:title" content="ignored">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"WebSite","name":"Veiled"},
{"@type":"Product","name":"Silk Bias Slip Skirt &amp; Tie","url":"https://veiled.shop/p/slip-skirt",
 "image":["//cdn.veiled.shop/a.jpg",{"url":"https://cdn.veiled.shop/b.jpg"}],"brand":{"@type":"Brand","name":"Veiled"},
 "description":"<p>Cut on the bias.</p>",
 "offers":[{"@type":"Offer","price":"240.00","priceCurrency":"USD","availability":"https://schema.org/OutOfStock"},
           {"@type":"Offer","price":"185.00","priceCurrency":"USD","availability":"https://schema.org/InStock"}]}]}
</script></head></html>'''
OPEN_GRAPH = '''<meta property="og:title" content="Linen Wrap Top"><meta property="og:image" content="https://x.co/t.jpg">
<meta property="product:price:amount" content="1,120.50"><meta property="product:price:currency" content="usd">'''


def test_reads_json_ld_products_from_any_platform():
    [p] = webshops.products(SQUARESPACE, 'https://veiled.shop/p/slip-skirt?ref=g')
    assert p['title'] == 'Silk Bias Slip Skirt & Tie' and p['url'] == 'https://veiled.shop/p/slip-skirt'
    assert (p['price'], p['currency'], p['available']) == (185.0, 'USD', True)  # the in-stock offer wins
    assert p['image_urls'] == ['https://cdn.veiled.shop/a.jpg', 'https://cdn.veiled.shop/b.jpg']
    assert p['brand'] == 'Veiled' and 'bias' in p['description'] and '<p>' not in p['description']


def test_falls_back_to_open_graph_price_tags():
    [p] = webshops.products(OPEN_GRAPH, 'https://shop.example/top')
    assert (p['title'], p['price'], p['currency']) == ('Linen Wrap Top', 1120.5, 'USD')
    assert webshops.products('<html>a blog post</html>', 'https://x.example/') == []


def test_only_independent_sites_count():
    assert webshops.independent('https://batulthecollection.com/products/x')
    assert webshops.independent('https://www.veiled.shop/p/1')
    for big in ('https://www.etsy.com/listing/1', 'https://www.nordstrom.com/s/x', 'https://www.zara.com/us/x',
                'https://www.pinterest.com/pin/1', 'https://shop.lululemon.com/p/1', 'https://www.vogue.com/a'):
        assert not webshops.independent(big), big


class FakeBrightData(webshops.WebShops):
    def __init__(self, serp, pages):
        super().__init__(Settings(brightdata_serp_zone='s', brightdata_unlocker_zone='u'))
        self.serp_rows, self.pages, self.searched, self.read = serp, pages, [], []

    async def serp(self, http, query):
        self.searched.append(query)
        return self.serp_rows.get(query, [])

    async def unlock(self, http, url):
        self.read.append(url)
        return self.pages[url]


def test_search_finds_indie_pages_and_the_shoppers_own_shops():
    own = IndieShop(domain='veiled.shop', name='Veiled', platform='web')
    shopify = IndieShop(domain='batulthecollection.com', name='Batul')
    web = FakeBrightData({
        'slip skirt independent designer label': [{'link': 'https://www.etsy.com/listing/1'},
                                                   {'link': 'https://indie.example/skirt'}],
        'site:veiled.shop slip skirt': [{'link': 'https://veiled.shop/p/slip-skirt'}]},
        {'https://indie.example/skirt': OPEN_GRAPH, 'https://veiled.shop/p/slip-skirt': SQUARESPACE})
    rows, summary = asyncio.run(web.search(['slip skirt'], 10, 200, [own, shopify]))
    assert 'site:batulthecollection.com slip skirt' not in web.searched  # Shopify shops are niche-indie's
    assert 'https://www.etsy.com/listing/1' not in web.read
    assert [r.title for r in rows] == ['Silk Bias Slip Skirt & Tie']  # the $1,120 top is over the cap
    assert rows[0].retailer == 'Veiled' and rows[0].tier == 'small_shop' and rows[0].source == 'web'
    assert summary['pages_with_products'] == 2


def test_searches_add_the_web_source_once_bright_data_is_set_up(tmp_path):
    from fastapi.testclient import TestClient
    from app import create_app

    def sources(**zones):
        settings = Settings(database_path=str(tmp_path/f'{len(zones)}.sqlite'), upload_dir=str(tmp_path/'u'), **zones)
        with TestClient(create_app(settings)) as client:
            pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
            client.put(f'/v1/taste/profiles/{pid}/notes', json={'notes': ['bias cut skirts']})
            client.post(f'/v1/taste/profiles/{pid}/build')
            job = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'skirt'}).json()['search_id']
        with Store(settings.database_path).connect() as db:
            return json.loads(db.execute('SELECT request FROM jobs WHERE id=?', (job,)).fetchone()[0])['sources']
    assert 'web' not in sources()
    assert sources(brightdata_serp_zone='s', brightdata_unlocker_zone='u')[-1] == 'web'
