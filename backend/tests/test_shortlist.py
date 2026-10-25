import time
import pytest
from fastapi.testclient import TestClient
from app import create_app
from sourcing.config import Settings
from taste.shortlist import describe, differences
from tests.test_taste import png


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=str(tmp_path / 's.sqlite'), upload_dir=str(tmp_path / 'up'))
    with TestClient(create_app(settings)) as client:
        yield client


def finished_search(client):
    pid = client.post('/v1/taste/profiles', json={'data_consent': True, 'name': 'Maya'}).json()['profile']['id']
    client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
    client.post(f'/v1/taste/profiles/{pid}/build')
    started = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'black top'}).json()
    for _ in range(200):
        job = client.get(started['status_url']).json()
        if job['status'] in ('completed', 'partial', 'failed'):
            break
        time.sleep(0.05)
    assert len(job['results']) > 1
    return pid, started['search_id'], job['results']


def test_saving_a_result_shortlists_it_and_teaches_the_taste_profile(client):
    pid, search_id, results = finished_search(client)
    saved = client.post(f'/v1/taste/profiles/{pid}/shortlist',
                        json={'search_id': search_id, 'listing_id': results[0]['id'], 'collection': ' Work  fits '}).json()
    assert saved['added'] and saved['item']['collection'] == 'Work fits' and saved['item']['category']
    assert saved['item']['listing']['url'] == results[0]['url']  # copied from the stored search, not the browser
    profile = client.get(f'/v1/taste/profiles/{pid}').json()['profile']
    assert profile['learned_notes'] == [saved['learned']] and saved['learned'].startswith('Shortlisted')
    # Saving it again doesn't duplicate the item or the learning.
    again = client.post(f'/v1/taste/profiles/{pid}/shortlist', json={'search_id': search_id, 'listing_id': results[0]['id']}).json()
    assert not again['added'] and again['item']['id'] == saved['item']['id']
    view = client.get(f'/v1/taste/profiles/{pid}/shortlist').json()
    assert len(view['items']) == 1 and view['collections'] == ['Work fits']


def test_collections_sort_items_and_deleting_one_keeps_its_items(client):
    pid, search_id, results = finished_search(client)
    item = client.post(f'/v1/taste/profiles/{pid}/shortlist', json={'search_id': search_id, 'listing_id': results[1]['id']}).json()['item']
    assert item['collection'] is None
    client.post(f'/v1/taste/profiles/{pid}/collections', json={'name': 'Summer'})
    moved = client.put(f'/v1/taste/profiles/{pid}/shortlist/{item["id"]}', json={'collection': 'Summer'}).json()
    assert moved['items'][0]['collection'] == 'Summer'
    after = client.delete(f'/v1/taste/profiles/{pid}/collections/Summer').json()
    assert after['collections'] == [] and after['items'][0]['collection'] is None
    assert client.delete(f'/v1/taste/profiles/{pid}/shortlist/{item["id"]}').json()['items'] == []


def test_add_to_taste_learns_without_shortlisting(client):
    pid, search_id, results = finished_search(client)
    out = client.post(f'/v1/taste/profiles/{pid}/liked', json={'search_id': search_id, 'listing_id': results[0]['id']}).json()
    assert out['learned'].startswith('Loved') and out['profile']['learned_notes'] == [out['learned']]
    assert client.get(f'/v1/taste/profiles/{pid}/shortlist').json()['items'] == []
    # The shopper can take a learning back off their taste profile.
    cleared = client.put(f'/v1/taste/profiles/{pid}/learned', json={'notes': []}).json()
    assert cleared['profile']['learned_notes'] == []


def test_someone_elses_search_cant_be_saved(client):
    pid, search_id, results = finished_search(client)
    other = client.post('/v1/taste/profiles', json={'name': 'Sam'}).json()['profile']['id']
    response = client.post(f'/v1/taste/profiles/{other}/shortlist', json={'search_id': search_id, 'listing_id': results[0]['id']})
    assert response.status_code == 404


def test_differences_name_what_the_pick_had_that_the_rest_didnt():
    picked = {'title': 'Cropped burgundy linen top', 'price': 22, 'source': 'secondhand', 'tier': 'resale', 'brand': None}
    others = [{'title': f'Black cotton top {i}', 'price': 60, 'source': 'mainstream', 'tier': 'mainstream', 'brand': 'Gap'}
              for i in range(5)]
    parts = differences(picked, others)
    assert any('cheaper' in p for p in parts) and 'secondhand' in parts
    assert any('burgundy' in p and 'linen' in p for p in parts)
    assert 'close to the other results' in describe(others[0], others[1:], 'top')


def test_streamed_result_can_be_liked_while_search_is_running(client, tmp_path):
    import sqlite3
    pid, search_id, results = finished_search(client)
    # A streamed job already stores its visible listings before all sources have finished.
    with sqlite3.connect(tmp_path / 's.sqlite') as db:
        db.execute("UPDATE jobs SET status='running' WHERE id=?", (search_id,))
    response = client.post(f'/v1/taste/profiles/{pid}/liked', json={'search_id': search_id, 'listing_id': results[0]['id']})
    assert response.status_code == 200
    assert response.json()['learned'].startswith('Loved')
