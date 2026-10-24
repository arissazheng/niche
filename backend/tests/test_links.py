import asyncio
import httpx
import pytest
from fastapi.testclient import TestClient
from app import create_app
from sourcing import safe_fetch
from sourcing.config import Settings
from taste.links import LinkedItem, extract_urls, parse_meta
from tests.test_taste import png

PAGE = '''<html><head><title>Fallback title | Shop</title>
<meta property="og:title" content="Vintage Y2K Pinstripe Halter Vest">
<meta property="og:description" content="Charcoal pinstripe, button front, size L.">
<meta property="og:image" content="/img/p0.jpg">
<meta property="og:site_name" content="Depop">
</head><body></body></html>'''

LD_PAGE = '''<html><head><title>Etsy listing</title>
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},
{"@type":"Product","name":"Hand-knit mohair cardigan","description":"Cropped, cream, chunky knit.",
"image":[{"url":"https://i.etsystatic.com/1.jpg"}]}]}</script></head></html>'''


def test_extract_urls_strips_punctuation_dedupes_and_limits():
    text = ('find me something like https://www.depop.com/products/abc-123/, or (https://x.example/a) '
            'and https://www.depop.com/products/abc-123/ and https://third.example/z')
    assert extract_urls(text) == ['https://www.depop.com/products/abc-123/', 'https://x.example/a']
    assert extract_urls('no links here') == []


def test_parse_meta_open_graph_and_json_ld():
    meta = parse_meta(PAGE, 'https://www.depop.com/products/abc/')
    assert meta == {'title': 'Vintage Y2K Pinstripe Halter Vest', 'description': 'Charcoal pinstripe, button front, size L.',
                    'image_url': 'https://www.depop.com/img/p0.jpg', 'site': 'Depop', 'product': False}
    ld = parse_meta(LD_PAGE, 'https://www.etsy.com/listing/1')
    assert ld['title'] == 'Hand-knit mohair cardigan' and ld['image_url'] == 'https://i.etsystatic.com/1.jpg'
    assert ld['site'] == 'etsy.com' and ld['product'] is True
    assert parse_meta('<title>Only a title</title>', 'https://a.example/')['title'] == 'Only a title'


@pytest.mark.parametrize('url', ['http://127.0.0.1:3100/v1', 'http://10.0.0.5/', 'http://169.254.169.254/latest/meta-data',
                                 'http://[::1]/', 'http://[::ffff:127.0.0.1]/', 'ftp://example.com/', 'http://user:pw@example.com/'])
def test_check_rejects_non_public_targets(url):
    with pytest.raises(safe_fetch.UnsafeURL):
        asyncio.run(safe_fetch.check(url))


def fake_dns(monkeypatch, table):
    async def resolve(host):
        return table[host]
    monkeypatch.setattr(safe_fetch, 'resolve', resolve)


def test_check_uses_dns(monkeypatch):
    fake_dns(monkeypatch, {'shop.example': ['93.184.216.34'], 'internal.example': ['10.1.2.3']})
    asyncio.run(safe_fetch.check('https://shop.example/p/1'))
    with pytest.raises(safe_fetch.UnsafeURL):
        asyncio.run(safe_fetch.check('https://internal.example/'))


def run_fetch(handler, url, max_bytes=1000):
    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False) as http:
            return await safe_fetch.fetch(http, url, max_bytes)
    return asyncio.run(go())


def test_fetch_refuses_redirect_into_private_network(monkeypatch):
    fake_dns(monkeypatch, {'shop.example': ['93.184.216.34'], 'evil.example': ['169.254.169.254']})
    hits = []

    def handler(request):
        hits.append(request.url.host)
        if request.url.host == 'shop.example':
            return httpx.Response(302, headers={'location': 'http://evil.example/latest/meta-data'})
        return httpx.Response(200, text='secret')
    assert run_fetch(handler, 'https://shop.example/p/1') is None
    assert hits == ['shop.example']  # the private target was never requested


def test_fetch_follows_public_redirects_and_caps_size(monkeypatch):
    fake_dns(monkeypatch, {'a.example': ['93.184.216.34'], 'b.example': ['93.184.216.35']})

    def handler(request):
        if request.url.host == 'a.example':
            return httpx.Response(301, headers={'location': 'https://b.example/final'})
        return httpx.Response(200, text='x' * 500, headers={'content-type': 'text/html'})
    body, final_url, kind = run_fetch(handler, 'https://a.example/start')
    assert len(body) == 500 and final_url == 'https://b.example/final' and 'html' in kind
    assert run_fetch(handler, 'https://a.example/start', max_bytes=100) is None


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=str(tmp_path/'api.sqlite'), upload_dir=str(tmp_path/'uploads'))
    with TestClient(create_app(settings)) as client:
        yield client


def built_profile(client):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
    client.post(f'/v1/taste/profiles/{pid}/build')
    return pid


def test_chat_with_link_proposes_similar_search(client, monkeypatch):
    import taste.api
    read = []

    async def fake_read(url):
        read.append(url)
        return LinkedItem(url=url, site='Depop', title='Vintage Y2K Pinstripe Halter Vest', readable=True)
    monkeypatch.setattr(taste.api, 'read_link', fake_read)
    pid = built_profile(client)
    msg = {'messages': [{'role': 'user', 'text': 'find me something similar https://www.depop.com/products/abc/'}]}
    out = client.post(f'/v1/taste/profiles/{pid}/chat', json=msg).json()
    assert read == ['https://www.depop.com/products/abc/']
    assert out['action'] == 'propose' and 'Pinstripe Halter' in out['brief'] and 'search_id' not in out
    assert out['linked'][0]['title'] == 'Vintage Y2K Pinstripe Halter Vest' and 'image' not in out['linked'][0]


def test_chat_with_unreadable_link_asks_instead_of_guessing(client, monkeypatch):
    import taste.api

    async def fake_read(url):
        return LinkedItem(url=url, site='blocked.example')
    monkeypatch.setattr(taste.api, 'read_link', fake_read)
    pid = built_profile(client)
    msg = {'messages': [{'role': 'user', 'text': 'like this https://blocked.example/item/9'}]}
    out = client.post(f'/v1/taste/profiles/{pid}/chat', json=msg).json()
    assert out['action'] == 'reply' and 'describe' in out['reply'] and out['linked'][0]['readable'] is False


def test_live_agent_sees_linked_photo():
    from taste.chat import ChatTurn, ShopAgent
    from taste.models import Profile
    seen = {}

    class FakeModel:
        async def call(self, system, content, job_id, stage, max_tokens, schema=None, effort=None):
            seen['content'] = content
            return {'reply': 'Would you like me to search for charcoal pinstripe halters?', 'action': 'propose',
                    'brief': 'charcoal pinstripe halter vest, button front', 'max_item_price': None, 'size': None, 'must_have': [], 'brands': [], 'category': 'top'}
    photo = {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': 'AAAA'}}
    item = LinkedItem(url='https://d.example/p', title='Halter', readable=True, image=photo)
    agent = ShopAgent(Settings(taste_mode='live', anthropic_api_key='k'), FakeModel())
    turn = asyncio.run(agent.respond(Profile(id='p', prompt='y2k'), [ChatTurn(role='user', text='like this https://d.example/p')],
                                     linked=[item]))
    assert turn.action == 'propose'
    blocks = seen['content']
    assert isinstance(blocks, list) and blocks[-1] == photo and '"linked_items"' in blocks[0]['text']
    assert 'AAAA' not in blocks[0]['text']  # the photo goes as an image block, not inside the JSON


def test_read_link_needs_product_evidence(monkeypatch):
    import taste.links as links

    async def fake_fetch(http, url, max_bytes):
        pages = {'https://parked.example/': '<title>Casino bonus</title><meta name="description" content="Win big">',
                 'https://shop.example/p/1': '<meta property="og:type" content="product"><meta property="og:title" content="Wool coat">'}
        return pages[url].encode(), url, 'text/html'
    monkeypatch.setattr(links.safe_fetch, 'fetch', fake_fetch)
    assert asyncio.run(links.read_link('https://parked.example/')).readable is False
    coat = asyncio.run(links.read_link('https://shop.example/p/1'))
    assert coat.readable is True and coat.title == 'Wool coat' and coat.image is None
