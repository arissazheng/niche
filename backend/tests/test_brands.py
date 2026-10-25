import asyncio
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from app import create_app
from sourcing.config import Settings
from sourcing.models import IndieShop
from taste import brands, shops
from actors.niche_actors.labels import SMALL_CATALOG

TODAY = datetime(2026, 10, 24, tzinfo=timezone.utc)
LABEL = IndieShop(domain='velathelabel.com', name='Vela')


def product(i, vendor='Vela', published='2024-03-01T10:00:00-08:00', available=True):
    return {'id': i, 'vendor': vendor, 'published_at': published,
            'variants': [{'price': '120.00', 'available': available}]}


def test_a_small_established_label_passes_every_check():
    result = brands.checks(LABEL, [product(1), product(2, published='2026-10-01T00:00:00Z')], TODAY)
    assert result == dict.fromkeys(brands.CHECKS, True)


def test_each_check_catches_its_case():
    new_store = brands.checks(LABEL, [product(1, published='2026-09-30T00:00:00Z')], TODAY)
    assert not new_store['established']  # a month old: often a drop-shipping store
    boutique = brands.checks(LABEL, [product(i, vendor=f'Brand {"ABCDEFGHIJKL"[i]}') for i in range(12)], TODAY)
    assert not boutique['own_label']  # resells twelve labels
    sold_out = brands.checks(LABEL, [product(1, available=False)], TODAY)
    assert not sold_out['real_store']
    huge = brands.checks(LABEL, [product(i) for i in range(SMALL_CATALOG)], TODAY)
    assert not huge['small']
    chain = brands.checks(IndieShop(domain='zara.com', name='Zara'), [product(1)], TODAY)
    assert not chain['independent']
    web = brands.checks(IndieShop(domain='veiled.shop', name='Veiled', platform='web'), [], TODAY)
    assert set(web.values()) == {None}


def test_verify_fills_in_the_result(monkeypatch):
    async def catalog(http, domain):
        return [product(1)] if domain == 'velathelabel.com' else [product(1, published='2026-10-20T00:00:00Z')]
    monkeypatch.setattr(brands, 'catalog', catalog)
    good = asyncio.run(brands.verify(LABEL, http=object()))
    assert good.verified is True and good.checks['established']
    new = asyncio.run(brands.verify(IndieShop(domain='newdrop.com', name='New Drop'), http=object()))
    assert new.verified is False
    web = asyncio.run(brands.verify(IndieShop(domain='veiled.shop', name='Veiled', platform='web'), http=object()))
    assert web.verified is None


class FakeClaude:
    def __init__(self):
        self.asked = None

    async def call(self, system, content, job_id, stage, max_tokens, schema=None, effort=None):
        self.asked = content
        return {'brands': [{'name': 'Vela', 'website': 'velathelabel.com', 'reason': 'Bias-cut satin like you save'},
                           {'name': 'Invented', 'website': 'invented-label.com', 'reason': 'x'},
                           {'name': 'New Drop', 'website': 'newdrop.com', 'reason': 'x'}]}


def test_discovery_only_shows_verified_labels(monkeypatch):
    async def find(text, http=None, any_platform=False):
        return None if 'invented' in text else IndieShop(domain=text, name=text.split('.')[0])

    async def verify(shop, http=None):
        return shop.model_copy(update={'verified': shop.domain == 'velathelabel.com'})
    monkeypatch.setattr(shops, 'find', find)
    monkeypatch.setattr(brands, 'verify', verify)
    from taste.models import Onboarding, Profile
    profile = Profile(id='p', onboarding=Onboarding(favorite_brands=['Batul The Collection']), summary='slinky satin')
    model = FakeClaude()
    found = asyncio.run(brands.discover(model, profile, 'p', http=object()))
    assert [(s.domain, r) for s, r in found] == [('velathelabel.com', 'Bias-cut satin like you save')]
    assert 'Batul The Collection' in model.asked


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=str(tmp_path/'api.sqlite'), upload_dir=str(tmp_path/'uploads'))
    with TestClient(create_app(settings)) as client:
        yield client


def test_suggestions_endpoint_checks_once_per_profile_version(client, monkeypatch):
    calls = []

    async def verified_only(candidates, have=(), http=None):
        calls.append(candidates)
        return [(IndieShop(domain=candidates[0][0], name='Christy Dawn', verified=True), candidates[0][1])]
    monkeypatch.setattr(brands, 'verified_only', verified_only)
    pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    assert client.get(f'/v1/taste/profiles/{pid}/brands/suggestions').status_code == 422  # build first
    client.put(f'/v1/taste/profiles/{pid}/notes', json={'notes': ['prairie dresses']})
    client.post(f'/v1/taste/profiles/{pid}/build')
    first = client.get(f'/v1/taste/profiles/{pid}/brands/suggestions').json()['suggestions']
    assert first[0]['shop']['verified'] is True and first[0]['shop']['domain'] == 'christydawn.com'
    client.get(f'/v1/taste/profiles/{pid}/brands/suggestions')
    assert len(calls) == 1
