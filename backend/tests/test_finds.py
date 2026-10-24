import json
import time
import httpx
import pytest
from fastapi.testclient import TestClient
from app import create_app
from sourcing.config import Settings
from taste import finds as finds_module
from taste.finds import Finds, doc_text
from tests.test_taste import png


class FakeMoss:
    """Moss's manage and cloud query APIs, in memory. Query returns docs sharing the most words with the query."""

    def __init__(self):
        self.indexes: dict[str, dict[str, dict]] = {}
        self.calls = []

    def __call__(self, request: httpx.Request):
        body = json.loads(request.content)
        self.calls.append((request.url.path, body.get('action')))
        if request.url.path == '/query':
            docs = self.indexes.get(body['indexName'], {}).values()
            words = set(body['query'].lower().split())
            ranked = sorted(docs, key=lambda d: -len(words & set(d['text'].lower().split())))
            return httpx.Response(200, json={'docs': [{**d, 'score': .9} for d in ranked[:body['topK']]]})
        assert request.headers['x-project-key'] == 'moss-key' and body['projectId'] == 'moss-project'
        name = body.get('indexName')
        if body['action'] == 'getIndex':
            return httpx.Response(200, json={'name': name}) if name in self.indexes else httpx.Response(404, json={'error': 'Index not found'})
        if body['action'] in ('createIndex', 'addDocs'):
            self.indexes.setdefault(name, {}).update({d['id']: d for d in body['docs']})
            return httpx.Response(200, json=True)
        return httpx.Response(400, json={'error': 'unexpected'})


@pytest.fixture
def moss(monkeypatch):
    fake = FakeMoss()
    monkeypatch.setattr(finds_module, 'transport', httpx.MockTransport(fake))
    monkeypatch.setattr(Finds, '_sdk', lambda self: None)  # use the cloud query path, not an installed SDK
    return fake


@pytest.fixture
def client(tmp_path, moss):
    settings = Settings(database_path=str(tmp_path/'f.sqlite'), upload_dir=str(tmp_path/'up'),
                        moss_project_id='moss-project', moss_project_key='moss-key')
    with TestClient(create_app(settings)) as client:
        yield client


def wait_for(check, tries=80):
    for _ in range(tries):
        if check():
            return True
        time.sleep(.05)
    return False


def finished_search(client, pid, query):
    search = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': query, 'sources': ['etsy']}).json()
    assert wait_for(lambda: client.get(search['status_url']).json()['status'] in ('completed', 'partial'))
    return search['search_id']


def built_profile(client):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
    client.post(f'/v1/taste/profiles/{pid}/build')
    return pid


def test_shown_results_go_to_moss_and_come_back_later(client, moss):
    pid = built_profile(client)
    first = finished_search(client, pid, 'linen skirt')
    chat = f'/v1/taste/profiles/{pid}/chat'
    client.post(chat, json={'messages': [{'role': 'user', 'text': 'nice'}], 'search_id': first})
    name = f'niche-finds-{pid}'
    assert wait_for(lambda: len(moss.indexes.get(name, {})) > 0)
    doc = next(iter(moss.indexes[name].values()))
    assert doc['metadata']['search_id'] == first and doc['id'].startswith(f'{first}:') and 'linen skirt' in doc['text']

    second = finished_search(client, pid, 'boots')
    reply = client.post(chat, json={'messages': [{'role': 'user', 'text': 'show me the skirt from before'}],
                                    'search_id': second}).json()
    first_results = client.get(f'/v1/searches/{first}').json()['results']
    assert reply['action'] == 'reply' and reply['recalled']
    assert {r['url'] for r in reply['recalled']} <= {x['url'] for x in first_results}  # prices/links from the store
    assert set(reply['recalled'][0]) == {'title', 'url', 'price', 'currency', 'store'}
    # The agent turn, with its recalled finds, is accepted back as conversation history.
    history = [{'role': 'user', 'text': 'show me the skirt from before'},
               {'role': 'agent', 'text': reply['reply'], 'recalled': reply['recalled']},
               {'role': 'user', 'text': 'thanks'}]
    assert client.post(chat, json={'messages': history, 'search_id': second}).status_code == 200


def test_each_search_is_indexed_once(client, moss):
    pid = built_profile(client)
    first = finished_search(client, pid, 'skirt')
    for text in ('a', 'b', 'c'):
        client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': text}], 'search_id': first})
    assert wait_for(lambda: f'niche-finds-{pid}' in moss.indexes)
    writes = [c for c in moss.calls if c[1] in ('createIndex', 'addDocs')]
    assert len(writes) == 1


def test_another_shoppers_search_is_never_indexed_or_recalled(client, moss):
    owner, other = built_profile(client), built_profile(client)
    search = finished_search(client, owner, 'skirt')
    client.post(f'/v1/taste/profiles/{other}/chat', json={'messages': [{'role': 'user', 'text': 'hi'}], 'search_id': search})
    time.sleep(.2)
    assert f'niche-finds-{other}' not in moss.indexes


def test_moss_down_never_breaks_the_chat(client, monkeypatch):
    monkeypatch.setattr(finds_module, 'transport', httpx.MockTransport(lambda r: httpx.Response(503, text='down')))
    pid = built_profile(client)
    search = finished_search(client, pid, 'skirt')
    r = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'the one from before'}],
                                                             'search_id': search})
    assert r.status_code == 200 and 'recalled' not in r.json()


def test_moss_off_without_keys(tmp_path, monkeypatch):
    def fail(request):
        raise AssertionError('Moss called without keys')
    monkeypatch.setattr(finds_module, 'transport', httpx.MockTransport(fail))
    with TestClient(create_app(Settings(database_path=str(tmp_path/'o.sqlite'), upload_dir=str(tmp_path/'up')))) as client:
        pid = built_profile(client)
        search = finished_search(client, pid, 'skirt')
        assert client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'from before?'}],
                                                                    'search_id': search}).status_code == 200


def test_doc_text_reads_like_a_description():
    text = doc_text({'title': 'Green linen midi skirt', 'retailer': None, 'seller': 'vintagebyamy', 'source': 'etsy',
                     'price': 42.0, 'currency': 'USD', 'condition': 'used', 'brand': None, 'reason': 'Matches your greens'},
                    'linen skirt')
    assert text == 'Green linen midi skirt. from vintagebyamy. 42 USD. used. Matches your greens. searched for: linen skirt'
