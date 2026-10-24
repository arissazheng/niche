import httpx
import pytest
from fastapi.testclient import TestClient
from app import create_app
from sourcing.config import Settings
from voice import api as voice

SHOPS = ['Depop', 'Etsy', 'Thrift stores', 'Big retailers']


def make_client(tmp_path, **settings):
    return TestClient(create_app(Settings(database_path=str(tmp_path/'v.sqlite'), upload_dir=str(tmp_path/'up'), **settings)))


@pytest.fixture
def cartesia(monkeypatch):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'type': 'transcript', 'is_final': True, 'text': ' make it more vintage '})
    monkeypatch.setattr(voice, 'transport', httpx.MockTransport(handler))
    return seen


def test_transcribe_sends_audio_to_cartesia_with_server_key(tmp_path, cartesia):
    with make_client(tmp_path, cartesia_api_key='sk_test') as client:
        assert client.get('/v1/voice/status').json() == {'enabled': True, 'provider': 'cartesia'}
        r = client.post('/v1/voice/transcribe', files={'file': ('speech.webm', b'opus-bytes', 'audio/webm')})
    assert r.status_code == 200 and r.json() == {'text': 'make it more vintage'}
    sent = cartesia[0]
    assert str(sent.url) == 'https://api.cartesia.ai/stt'
    assert sent.headers['authorization'] == 'Bearer sk_test' and sent.headers['cartesia-version']
    assert b'ink-whisper' in sent.content and b'opus-bytes' in sent.content


def test_voice_off_without_key(tmp_path, cartesia):
    with make_client(tmp_path) as client:
        assert client.get('/v1/voice/status').json()['enabled'] is False
        r = client.post('/v1/voice/transcribe', files={'file': ('speech.webm', b'x', 'audio/webm')})
    assert r.status_code == 503 and not cartesia


def test_cartesia_error_is_reported_plainly(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, 'transport', httpx.MockTransport(lambda r: httpx.Response(401, text='bad key sk_test')))
    with make_client(tmp_path, cartesia_api_key='sk_test') as client:
        r = client.post('/v1/voice/transcribe', files={'file': ('speech.webm', b'x', 'audio/webm')})
    assert r.status_code == 502 and 'sk_test' not in r.text


def test_empty_recording_rejected(tmp_path, cartesia):
    with make_client(tmp_path, cartesia_api_key='sk_test') as client:
        r = client.post('/v1/voice/transcribe', files={'file': ('speech.webm', b'', 'audio/webm')})
    assert r.status_code == 400 and not cartesia


def test_onboarding_fixture_parse(tmp_path):
    text = ("Hi, I'm Dana. I'm 25. My email is Dana@example.com and I usually shop at Depop and thrift stores. "
            'My budget is $50 to $200.')
    with make_client(tmp_path) as client:
        heard = client.post('/v1/voice/onboarding', json={'transcript': text, 'shop_options': SHOPS}).json()
    assert heard == {'name': 'Dana', 'age': 25, 'email': 'dana@example.com', 'budget_min': 50, 'budget_max': 200,
                     'usual_shops': ['Depop', 'Thrift stores']}


def test_onboarding_only_returns_what_was_said(tmp_path):
    with make_client(tmp_path) as client:
        heard = client.post('/v1/voice/onboarding', json={'transcript': 'keep it under 80 dollars', 'shop_options': SHOPS}).json()
    assert heard == {'budget_max': 80}


def test_clean_drops_values_the_form_would_reject():
    heard = voice.Heard(name=' Ari ', age=7, email='not-an-email', budget_min=-1, budget_max=0, currency='usd',
        usual_shops=['Depop', 'Made Up'], favorite_brands=['Zara'],
        measurements=voice.HeardMeasurements(unit='feet', shoulder=None, bust=None, waist=999, hips=None, inseam=None, arm=None))
    out = voice.clean(heard, SHOPS).model_dump(exclude_none=True)
    assert out == {'name': 'Ari', 'usual_shops': ['Depop'], 'favorite_brands': ['Zara']}
