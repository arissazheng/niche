import asyncio
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
    profile = client.post('/v1/taste/profiles', json={'name': 'Ari', 'budget_max': 80}).json()['profile']
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
    intent = client.post('/v1/checkout/intents', json={'search_id': search.json()['search_id'],
        'listing_id': result['results'][0]['id']}).json()
    assert intent['mode'] == 'fixture' and intent['amount'] == round(result['results'][0]['price'] * 100)
    assert client.post('/v1/checkout/intents', json={'search_id': search.json()['search_id'],
        'listing_id': 'invented'}).status_code == 404


def test_rejects_bad_uploads_and_empty_builds(client):
    pid = client.post('/v1/taste/profiles', json={}).json()['profile']['id']
    assert client.post(f'/v1/taste/profiles/{pid}/build').status_code == 422
    assert client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'x'}).status_code == 422
    bad = client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', b'not an image')})
    assert bad.status_code == 422


def test_live_build_drops_invented_image_ids(tmp_path):
    settings = Settings(database_path=str(tmp_path/'t.sqlite'), upload_dir=str(tmp_path/'u'), taste_mode='live',
        anthropic_api_key='test')
    taste = TasteStore(Store(settings.database_path))
    stages = []

    class FakeModel:
        async def call(self, system, content, job_id, stage, max_tokens, schema=None):
            stages.append(stage)
            if stage == 'extract':
                assert content[0]['type'] == 'image'
                return {'garments': [], 'aesthetic_tags': ['minimal'], 'liked_aspects': [], 'disliked_aspects': [],
                        'confidence_notes': []}
            ids = [x['source'] for x in content if x['type'] == 'image']
            assert ids
            return {'summary': 's', 'clusters': [{'name': 'c', 'description': 'd', 'image_ids': [image.id, 'made-up'],
                    'colors': [], 'silhouettes': [], 'patterns': []}], 'colors': ['olive'], 'silhouettes': [],
                    'patterns': [], 'materials': [], 'designers': [], 'aesthetics': [], 'avoid': ['frills'], 'prompt': 'p'}

    engine = TasteEngine(settings, taste, model=FakeModel())
    profile = taste.create_profile(Onboarding())
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
        async def call(self, system, content, job_id, stage, max_tokens, schema=None):
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
    provisional = [c for c in live.calls if c[0] == 'listings' and not c[2]]
    final = [c for c in live.calls if c[0] == 'listings' and c[2]]
    assert len(provisional) == 2 and all(c[1] > 0 for c in provisional)
    assert len(final) == 1 and final[0][3] == list(range(1, final[0][1] + 1))
    # Provisional copies must not leak duplicate warnings into the final results.
    result = store.get(job)['results'][0]
    assert len(result['warnings']) == len(set(result['warnings']))
