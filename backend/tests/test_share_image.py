import io
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from app import create_app
from sourcing.config import Settings
from tests.test_taste import png


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=str(tmp_path / 's.sqlite'), upload_dir=str(tmp_path / 'up'))
    with TestClient(create_app(settings)) as client:
        yield client


def test_share_image_is_a_story_or_square_png_for_the_owner_only(client):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True, 'name': 'Ari'}).json()['profile']['id']
    for color in ((20, 20, 20), (200, 30, 40), (240, 240, 240)):
        client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png(color))})
    assert client.get(f'/v1/taste/profiles/{pid}/share-image').status_code == 422  # build first
    client.post(f'/v1/taste/profiles/{pid}/build')
    for fmt, size in (('story', (1080, 1920)), ('square', (1080, 1080))):
        r = client.get(f'/v1/taste/profiles/{pid}/share-image', params={'format': fmt})
        assert r.status_code == 200 and r.headers['content-type'] == 'image/png'
        assert Image.open(io.BytesIO(r.content)).size == size
    assert client.get('/v1/taste/profiles/nope/share-image').status_code == 404
    token = client.post(f'/v1/taste/profiles/{pid}/share').json()['token']
    # A share token isn't a profile id, so a friend can't fetch the owner's share picture with it.
    assert client.get(f'/v1/taste/profiles/{token}/share-image').status_code == 404
    assert client.get(f'/v1/taste/shared/{token}/share-image').status_code in (404, 405)
