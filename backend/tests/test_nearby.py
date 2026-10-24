import pytest
from fastapi.testclient import TestClient
from app import create_app
from sourcing.config import Settings
from taste import nearby as nearby_module
from taste.nearby import parse


def reply(text, places):
    return {'steps': [{'type': 'model_output', 'content': [{'type': 'text', 'text': text, 'annotations': [
        {'type': 'place_citation', 'name': n, 'url': f'https://maps.google.com/?cid={i}'} for i, n in enumerate(places)]}]}]}


def test_only_shops_with_a_google_maps_source_are_kept():
    shops = parse(reply('1. **Mars Mercantile** — vintage eveningwear and 90s satin\n'
                        'Made Up Boutique — cheerful invented shop\n'
                        'Crossroads Trading — consignment with current labels',
                        ['Review of Mars Mercantile - Google Maps', 'Mars Mercantile - Google Maps', 'Crossroads Trading Co']))
    assert [s['name'] for s in shops] == ['Mars Mercantile', 'Crossroads Trading Co']
    assert shops[0]['why'] == 'vintage eveningwear and 90s satin' and shops[0]['maps_url'].startswith('https://maps.google')


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=str(tmp_path / 'n.sqlite'), upload_dir=str(tmp_path / 'up'), gemini_api_key='k')
    with TestClient(create_app(settings)) as client:
        yield client


def test_nearby_is_off_unless_opted_in_with_a_zip(client, monkeypatch):
    sent = {}

    async def shops(self, zip_code, brief):
        sent.update(zip=zip_code, brief=brief)
        return [{'name': 'Mars Mercantile', 'why': 'vintage', 'maps_url': 'https://maps.google.com/?cid=1'}]

    monkeypatch.setattr(nearby_module.Nearby, 'shops', shops)
    from tests.test_taste import png
    pid = client.post('/v1/taste/profiles', json={'data_consent': True, 'name': 'Ari'}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
    client.post(f'/v1/taste/profiles/{pid}/build')
    search_id = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'black satin dress'}).json()['search_id']
    assert client.get(f'/v1/taste/profiles/{pid}/nearby', params={'search_id': search_id}).json() == {'enabled': False, 'shops': []}
    profile = client.get(f'/v1/taste/profiles/{pid}').json()['profile']
    client.put(f'/v1/taste/profiles/{pid}/onboarding', json={**profile['onboarding'], 'nearby_shops': True, 'zip_code': '94704'})
    out = client.get(f'/v1/taste/profiles/{pid}/nearby', params={'search_id': search_id}).json()
    assert out['shops'][0]['name'] == 'Mars Mercantile' and sent == {'zip': '94704', 'brief': 'black satin dress'}
    assert 'Ari' not in str(sent)  # only the ZIP and the brief leave Niche
    other = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    assert client.get(f'/v1/taste/profiles/{other}/nearby', params={'search_id': search_id}).json()['enabled'] is False
