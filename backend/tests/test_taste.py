import asyncio
import json
import io
import time
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app import create_app
from sourcing.config import Settings
from sourcing.store import Store
from taste.engine import TasteEngine
from taste.models import Onboarding
from taste.store import TasteStore


def png(color):
    out = io.BytesIO()
    Image.new('RGB', (64, 64), color).save(out, format='PNG')
    return out.getvalue()


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=str(tmp_path/'api.sqlite'), upload_dir=str(tmp_path/'uploads'))
    with TestClient(create_app(settings)) as client:
        yield client


def test_fixture_flow_profile_to_checkout(client):
    profile = client.post('/v1/taste/profiles', json={'data_consent': True, 'name': 'Ari', 'budget_max': 80}).json()['profile']
    pid = profile['id']
    upload = client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((120, 130, 60)))},
        data={'kind': 'outfit'})
    assert upload.status_code == 201 and upload.json()['palette'][0] == '#78823c'
    image = upload.json()['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('b.png', png((240, 235, 220)))}, data={'kind': 'item'})
    assert client.put(f'/v1/taste/images/{image}/note', json={'note': 'I like the color, not the frills'}).status_code == 200
    built = client.post(f'/v1/taste/profiles/{pid}/build').json()
    assert built['profile']['mode'] == 'fixture' and 'not the frills' in built['profile']['prompt']
    assert {i for c in built['profile']['clusters'] for i in c['image_ids']} == {x['id'] for x in built['images']}
    edited = client.post(f'/v1/taste/profiles/{pid}/edit', json={'instruction': 'more vintage', 'source': 'voice'}).json()
    assert edited['profile']['version'] == 2 and 'more vintage' in edited['profile']['prompt']
    search = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'trousers', 'sources': ['etsy']})
    assert search.status_code == 202
    url = search.json()['status_url']
    for _ in range(40):
        result = client.get(url).json()
        if result['status'] == 'completed':
            break
        time.sleep(.05)
    assert result['results'] and all(x['price'] <= 80 for x in result['results'])
    item = result['results'][0]
    bought = client.post('/v1/checkout/mark-bought', json={'search_id': search.json()['search_id'], 'listing_id': item['id']})
    assert bought.status_code == 200 and bought.json() == {'recorded': False, 'reason': 'no_linked_bank', 'ledger': None}
    again = client.post('/v1/checkout/mark-bought', json={'search_id': search.json()['search_id'], 'listing_id': item['id']})
    assert again.json()['reason'] == 'already_marked'
    assert client.post('/v1/checkout/mark-bought', json={'search_id': search.json()['search_id'],
        'listing_id': 'invented'}).status_code == 404


def test_rejects_bad_uploads_and_empty_builds(client):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    assert client.post(f'/v1/taste/profiles/{pid}/build').status_code == 422
    assert client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'x'}).status_code == 422
    bad = client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', b'not an image')})
    assert bad.status_code == 422


def test_build_needs_consent(client):
    pid = client.post('/v1/taste/profiles', json={}).json()['profile']['id']
    assert client.post(f'/v1/taste/profiles/{pid}/build').status_code == 403
    client.put(f'/v1/taste/profiles/{pid}/onboarding', json={'data_consent': True})
    assert client.post(f'/v1/taste/profiles/{pid}/build').status_code == 422  # consented, but no photos yet


def test_live_build_drops_invented_image_ids(tmp_path):
    settings = Settings(database_path=str(tmp_path/'t.sqlite'), upload_dir=str(tmp_path/'u'), taste_mode='live',
        anthropic_api_key='test')
    taste = TasteStore(Store(settings.database_path))
    stages = []

    class FakeModel:
        async def call(self, system, content, job_id, stage, max_tokens, schema=None, effort=None):
            stages.append(stage)
            if stage == 'extract':
                assert content[0]['type'] == 'image'
                return {'garments': [], 'aesthetic_tags': ['minimal'], 'liked_aspects': [], 'disliked_aspects': [],
                        'confidence_notes': []}
            ids = [x['source'] for x in content if x['type'] == 'image']
            assert ids
            sent = json.dumps([x.get('text', '') for x in content if x['type'] == 'text'])
            assert 'ari@example.com' not in sent and 'Ari Z' not in sent  # no name/email sent to Claude
            return {'summary': 's', 'clusters': [{'name': 'c', 'description': 'd', 'image_ids': [image.id, 'made-up'],
                    'colors': [], 'silhouettes': [], 'patterns': []}], 'colors': ['olive'], 'silhouettes': [],
                    'patterns': [], 'materials': [], 'designers': [], 'aesthetics': [], 'avoid': ['frills'], 'prompt': 'p'}

    engine = TasteEngine(settings, taste, model=FakeModel())
    profile = taste.create_profile(Onboarding(name='Ari Z', email='ari@example.com'))
    image = engine.add_image(profile.id, png((10, 20, 30)), 'outfit')
    built = asyncio.run(engine.build(profile))
    assert stages == ['extract', 'synthesize']
    assert built.mode == 'claude' and built.clusters[0].image_ids == [image.id]
    assert built.to_sourcing().avoid == ['frills']


def test_palette_ignores_studio_background():
    from taste.palette import palette
    image = Image.new('RGB', (200, 260), (250, 250, 250))
    image.paste((40, 40, 45), (50, 40, 150, 220))       # charcoal garment
    image.paste((200, 30, 60), (80, 100, 110, 140))     # red detail
    colors = palette(image)
    assert colors == ['#28282d', '#c81e3c']


def test_live_build_redoes_fixture_analyses(tmp_path):
    from taste.engine import FIXTURE_NOTE
    settings = Settings(database_path=str(tmp_path/'t.sqlite'), upload_dir=str(tmp_path/'u'))
    taste = TasteStore(Store(settings.database_path))
    fixture = TasteEngine(settings, taste)
    profile = taste.create_profile(Onboarding())
    fixture.add_image(profile.id, png((10, 20, 30)), 'outfit')
    asyncio.run(fixture.build(profile))
    assert FIXTURE_NOTE in taste.images(profile.id)[0].analysis.confidence_notes
    stages = []

    class FakeModel:
        async def call(self, system, content, job_id, stage, max_tokens, schema=None, effort=None):
            stages.append(stage)
            if stage == 'extract':
                return {'garments': [{'category': 'skirt', 'colors': ['black'], 'silhouette': 'mini', 'pattern': 'solid',
                        'material': 'wool', 'details': [], 'designer': None}], 'aesthetic_tags': [], 'liked_aspects': [],
                        'disliked_aspects': [], 'confidence_notes': []}
            return {'summary': 's', 'clusters': [], 'colors': [], 'silhouettes': [], 'patterns': [], 'materials': [],
                    'designers': [], 'aesthetics': [], 'avoid': [], 'prompt': 'p'}

    live = TasteEngine(settings.model_copy(update={'taste_mode': 'live'}), taste, model=FakeModel())
    asyncio.run(live.build(taste.profile(profile.id)))
    assert stages == ['extract', 'synthesize']
    assert taste.images(profile.id)[0].analysis.garments[0].category == 'skirt'

    # Nothing changed: building again reuses the saved profile without calling Claude.
    before = taste.profile(profile.id)
    again = asyncio.run(live.build(before))
    assert stages == ['extract', 'synthesize'] and again.version == before.version
    # A new note changes the inputs, so the next build runs again.
    before.lookbook_notes = ['more denim']
    asyncio.run(live.build(taste.save_profile(before)))
    assert stages[-1] == 'synthesize' and len(stages) == 3


def test_photos_are_read_as_soon_as_they_are_added(tmp_path):
    settings = Settings(database_path=str(tmp_path/'t.sqlite'), upload_dir=str(tmp_path/'u'), taste_mode='live')
    taste = TasteStore(Store(settings.database_path))
    stages = []

    class FakeModel:
        async def call(self, system, content, job_id, stage, max_tokens, schema=None, effort=None):
            stages.append(stage)
            if stage == 'extract':
                return {'garments': [], 'aesthetic_tags': ['minimal'], 'liked_aspects': [], 'disliked_aspects': [],
                        'confidence_notes': []}
            return {'summary': 's', 'clusters': [], 'colors': [], 'silhouettes': [], 'patterns': [], 'materials': [],
                    'designers': [], 'aesthetics': [], 'avoid': [], 'prompt': 'p'}

    engine = TasteEngine(settings, taste, model=FakeModel())
    profile = taste.create_profile(Onboarding())

    async def add_then_build():
        engine.add_image(profile.id, png((10, 20, 30)), 'outfit')
        await asyncio.sleep(0.05)  # the background read finishes before Build is clicked
        assert taste.images(profile.id)[0].analysis.aesthetic_tags == ['minimal']
        await engine.build(taste.profile(profile.id))

    asyncio.run(add_then_build())
    assert stages == ['extract', 'synthesize']  # the photo was read once, in the background


class RecordingLive:
    def __init__(self):
        self.calls = []

    async def build_progress(self, *args):
        self.calls.append(('progress', args[1], args[2], args[3]))

    async def profile_version(self, profile_id, version):
        self.calls.append(('version', version))

    async def search(self, *args):
        self.calls.append(('search', args[3]))

    async def listings(self, search_id, items, replace=False):
        self.calls.append(('listings', len(items), replace, [x.get('rank') if isinstance(x, dict) else None for x in items]))


def test_live_publishing_for_build_and_search(tmp_path):
    from sourcing.models import SearchRequest
    from sourcing.pipeline import Pipeline
    from pathlib import Path
    settings = Settings(database_path=str(tmp_path/'t.sqlite'), upload_dir=str(tmp_path/'u'))
    store = Store(settings.database_path)
    taste = TasteStore(store)
    live = RecordingLive()
    engine = TasteEngine(settings, taste, publish=live)
    profile = taste.create_profile(Onboarding())
    engine.add_image(profile.id, png((10, 20, 30)), 'outfit')
    engine.add_image(profile.id, png((200, 20, 30)), 'item')
    asyncio.run(engine.build(profile))
    assert live.calls[0] == ('progress', 'extracting', 0, 2)
    assert ('progress', 'extracting', 2, 2) in live.calls
    assert live.calls[-2:] == [('version', 1), ('progress', 'done', 2, 2)]

    live.calls.clear()
    request = SearchRequest.model_validate_json(Path('examples/search.json').read_text())
    request.sources = ['etsy', 'depop']
    job = store.create(request.model_dump(mode='json'))
    asyncio.run(Pipeline(settings, store, live=live).run(request, job))
    assert live.calls[0] == ('search', 'running') and live.calls[-1] == ('search', 'completed')
    updates = [c for c in live.calls if c[0] == 'listings']
    # Each source shows up once ranked (never unranked) before the final set; every update refreshes the whole view.
    assert len(updates) >= 3 and all(c[2] for c in updates)
    assert not any(None in c[3] for c in updates if c[1])
    final = updates[-1]
    assert final[1] > 0 and final[3] == list(range(1, final[1] + 1))
    # Provisional copies must not leak duplicate warnings into the final results.
    result = store.get(job)['results'][0]
    assert len(result['warnings']) == len(set(result['warnings']))


def test_live_listing_row_carries_store_labels():
    from sourcing.live import listing_row
    row = listing_row({'id': 'secondhand:1', 'source': 'secondhand', 'title': 'Skirt', 'url': 'https://www.depop.com/p/1',
                       'image_urls': [], 'price': 30, 'currency': 'USD', 'warnings': [], 'score': None,
                       'retailer': 'Depop', 'tier': 'resale', 'marketplace': 'depop', 'brand': None})
    assert (row['retailer'], row['tier'], row['marketplace'], row['brand']) == ('Depop', 'resale', 'depop', '')
    assert row['score'] == {'none': []} and row['rank'] == {'none': []}


def test_chat_searches_requests_and_asks_before_its_own_ideas(client):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True, 'budget_max': 80}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))}, data={'kind': 'outfit'})
    assert client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'tops'}]}).status_code == 422
    client.post(f'/v1/taste/profiles/{pid}/build')
    turns = [{'role': 'user', 'text': 'i want an asymmetrical buttoned top'},
             {'role': 'agent', 'text': 'Searching.', 'brief': 'asymmetrical buttoned top'},
             {'role': 'user', 'text': 'no actually less formal'}]
    refined = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': turns}).json()
    assert refined['action'] == 'search' and 'less formal' in refined['brief'] and refined['search_id']  # no yes/no
    turns += [{'role': 'agent', 'text': refined['reply'], 'brief': refined['brief']},
              {'role': 'user', 'text': 'what do you think of cropped ones?'}]
    proposal = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': turns}).json()
    assert proposal['action'] == 'propose' and 'search_id' not in proposal
    turns += [{'role': 'agent', 'text': proposal['reply'], 'proposed': proposal['brief']},
              {'role': 'user', 'text': 'yes please'}]
    ran = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': turns}).json()
    assert ran['action'] == 'search' and ran['brief'] == proposal['brief'] and ran['search_id']
    assert client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': turns[:2]}).status_code == 422


def test_shop_agent_live_uses_claude_and_conversation(tmp_path):
    from taste.chat import ChatTurn, ShopAgent
    seen = {}

    class FakeModel:
        async def call(self, system, content, job_id, stage, max_tokens, schema=None, effort=None):
            seen.update(stage=stage, effort=effort, content=content)
            return {'reply': 'Searching relaxed ones now.', 'action': 'search',
                    'brief': 'asymmetrical buttoned top, relaxed casual style', 'max_item_price': None, 'size': None, 'must_have': ['asymmetric', 'button-front'], 'brands': [], 'category': 'top'}

    from taste.models import Profile
    agent = ShopAgent(Settings(taste_mode='live', anthropic_api_key='k'), FakeModel())
    turn = asyncio.run(agent.respond(Profile(id='p', prompt='monochrome y2k'),
        [ChatTurn(role='user', text='asymmetrical buttoned top'), ChatTurn(role='user', text='less formal')]))
    # The user asked for it, so the agent searches without a yes/no.
    assert turn.action == 'search' and 'relaxed' in turn.brief
    assert seen['stage'] == 'chat' and seen['effort'] == 'low' and 'less formal' in seen['content']


def test_pending_proposal_survives_a_reply_but_not_a_search():
    from taste.chat import ChatTurn as T, pending_proposal
    offered = [T(role='user', text='jacket'), T(role='agent', text='Search jackets?', proposed='leather jacket'),
               T(role='user', text='can i afford it?'), T(role='agent', text='Tight, but want me to run it?')]
    assert pending_proposal(offered + [T(role='user', text='yes')]).proposed == 'leather jacket'
    ran = offered + [T(role='user', text='yes'), T(role='agent', text='Searching.', brief='leather jacket')]
    assert pending_proposal(ran + [T(role='user', text='yes')]) is None


def test_chat_sees_numbered_results_of_own_search_only(client, monkeypatch):
    import time
    from taste import chat as chat_module
    seen = []

    async def fake_respond(self, profile, messages, budget=None, results=None, linked=None):
        seen.append(results)
        return chat_module.AgentTurn(reply='ok', action='reply', brief='', max_item_price=None, size=None, must_have=[], brands=[], category='other')
    monkeypatch.setattr(chat_module.ShopAgent, 'respond', fake_respond)
    pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
    client.post(f'/v1/taste/profiles/{pid}/build')
    search = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'skirt', 'sources': ['etsy']}).json()
    for _ in range(40):
        if client.get(search['status_url']).json()['status'] in ('completed', 'partial'):
            break
        time.sleep(.05)
    ask = {'messages': [{'role': 'user', 'text': 'what about #2?'}], 'search_id': search['search_id']}
    client.post(f'/v1/taste/profiles/{pid}/chat', json=ask)
    assert seen[-1][1]['n'] == 2 and seen[-1][1]['title'] and 'price' in seen[-1][1]
    other = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{other}/images', files={'file': ('a.png', png((20, 20, 20)))})
    client.post(f'/v1/taste/profiles/{other}/build')
    client.post(f'/v1/taste/profiles/{other}/chat', json=ask)
    assert seen[-1] is None  # another profile's search isn't shown to this agent


def test_size_matching_across_marketplace_labels():
    from sourcing.sizes import match
    assert all(match('S', x) for x in (['Small'], ['S/M'], ['XS-S'], ['US S'], ['One size']))
    assert not any(match('S', x) for x in (['L'], ['Large'], ['XL'], ['M']))
    assert match('S', []) is None and match('S', ['US 6']) is None  # unknown / other sizing system: keep, warn
    assert match('8', ['US 8']) and match('8', ['8.5']) is False


def test_pipeline_drops_other_sizes_and_flags_unknown():
    from pathlib import Path
    from sourcing.models import SearchRequest
    from sourcing.pipeline import eligible
    from sourcing.sources import FixtureSources
    request_data = SearchRequest.model_validate_json(Path('examples/search.json').read_text())
    items, _ = asyncio.run(FixtureSources().fetch('etsy', '', 4, ''))
    for item, labels in zip(items, (['Small'], ['L'], [], ['US 6'])):
        item.sizes = labels
    request_data.request.size = 'S'
    left_out = {}
    kept = {x.sizes[0] if x.sizes else None for x in eligible(items, request_data, left_out)}
    assert 'L' not in kept and 'Small' in kept
    assert left_out == {'wrong_size': 1}  # shown to the shopper as "1 in the wrong size"
    flagged = [x for x in eligible([items[3]], request_data)]
    assert any(w.startswith('Size unverified (listed as US 6') for w in flagged[0].warnings)


def test_chat_defaults_to_profile_size_for_the_garment(client):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True, 'sizes': {'top': 'S', 'bottom': 'M'}}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
    client.post(f'/v1/taste/profiles/{pid}/build')
    top = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'black halter top'}]}).json()
    pants = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'wide leg trousers'}]}).json()
    bag = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'black shoulder bag'}]}).json()
    assert (top['size'], pants['size'], bag['size']) == ('S', 'M', None)  # old flat sizes still work


def test_chat_accepts_history_with_linked_pages(client):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
    client.post(f'/v1/taste/profiles/{pid}/build')
    history = [{'role': 'user', 'text': 'like this?'},
               {'role': 'agent', 'text': 'Read it.', 'linked': [{'url': 'https://poshmark.com/listing/a', 'site': 'Poshmark',
                                                                   'title': 'Jacket', 'readable': True}]},
               {'role': 'user', 'text': 'black halter top'}]
    assert client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': history}).status_code == 200


def test_notes_only_lookbook_builds_and_own_fits_upload(client):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True, 'name': 'Ari'}).json()['profile']['id']
    assert client.post(f'/v1/taste/profiles/{pid}/build').status_code == 422  # nothing yet
    saved = client.put(f'/v1/taste/profiles/{pid}/notes', json={'notes': [' cropped brown leather jacket ', '', 'cropped brown leather jacket']})
    assert saved.json()['profile']['lookbook_notes'] == ['cropped brown leather jacket']
    built = client.post(f'/v1/taste/profiles/{pid}/build').json()
    assert 'cropped brown leather jacket' in built['profile']['prompt']
    own = client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('me.png', png((90, 60, 40)))}, data={'kind': 'own'})
    assert own.status_code == 201 and own.json()['kind'] == 'own' and own.json()['source'] == 'upload'


def test_numbered_bottom_size_and_length_reach_the_search(client):
    bad = client.post('/v1/taste/profiles', json={'data_consent': True, 'sizing': {'womens': {'bottoms': {'format': 'us', 'values': ['7']}}}})
    assert bad.status_code == 422
    sizing = {'system': 'womens', 'womens': {'tops': {'format': 'alpha', 'values': ['S']},
                                              'dresses': {'format': 'us', 'values': ['00'], 'extras': {'fit': 'Tall'}}}}
    pid = client.post('/v1/taste/profiles', json={'data_consent': True, 'sizing': sizing}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
    client.post(f'/v1/taste/profiles/{pid}/build')
    skirt = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'pleated midi skirt'}]}).json()
    top = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'black halter top'}]}).json()
    assert (skirt['size'], skirt['length']) == ('00', 'long') and top['length'] is None


def test_photos_need_a_signed_link_and_deleting_removes_the_file(client, tmp_path):
    from urllib.parse import urlsplit
    pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    image = client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))}).json()
    url = urlsplit(image['url'])
    assert client.get(f'{url.path}?{url.query}').status_code == 200
    assert client.get(url.path).status_code == 404  # bare link
    assert client.get(f'{url.path}?{url.query[:-4]}0000').status_code == 404  # tampered signature
    client.delete(f'/v1/taste/images/{image["id"]}')
    assert not (tmp_path/'uploads'/f'{image["id"]}.jpg').exists()


def test_delete_my_data_removes_profile_photos_and_searches(client, tmp_path):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    image = client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))}).json()
    client.post(f'/v1/taste/profiles/{pid}/build')
    search_id = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'black boots'}).json()['search_id']
    assert client.delete(f'/v1/taste/profiles/{pid}').status_code == 204
    assert client.get(f'/v1/taste/profiles/{pid}').status_code == 404
    assert not (tmp_path/'uploads'/f'{image["id"]}.jpg').exists()
    assert client.get(f'/v1/searches/{search_id}').status_code == 404
    assert client.delete(f'/v1/taste/profiles/{pid}').status_code == 404
