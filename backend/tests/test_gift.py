import pytest
from fastapi.testclient import TestClient
from app import create_app
from sourcing.config import Settings
from tests.test_taste import png


@pytest.fixture
def client(tmp_path):
    settings = Settings(database_path=str(tmp_path / 'g.sqlite'), upload_dir=str(tmp_path / 'up'))
    with TestClient(create_app(settings)) as client:
        yield client


def owner(client):
    pid = client.post('/v1/taste/profiles', json={
        'data_consent': True, 'name': 'Maya Chen', 'email': 'maya@example.com', 'age': 24, 'budget_max': 60,
        'nearby_shops': True, 'zip_code': '94704', 'measurements': {'waist': 26}}).json()['profile']['id']
    image = client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))}).json()
    client.put(f'/v1/taste/images/{image["id"]}/note', json={'note': 'my private note'})
    client.post(f'/v1/taste/profiles/{pid}/build')
    return pid


def test_shared_board_shows_the_taste_not_the_person(client):
    pid = owner(client)
    assert client.get('/v1/taste/shared/nope').status_code == 404  # not shared yet
    token = client.post(f'/v1/taste/profiles/{pid}/share').json()['token']
    assert client.post(f'/v1/taste/profiles/{pid}/share').json()['token'] == token  # same link until revoked
    board = client.get(f'/v1/taste/shared/{token}').json()
    text = str(board)
    assert board['profile']['onboarding']['name'] == 'Maya' and board['images'] and board['board_id']
    for private in (pid, 'maya@example.com', 'Chen', '94704', 'my private note', "'age': 24", 'share_token'):
        assert private not in text
    assert board['board_id'] == client.get(f'/v1/taste/profiles/{pid}').json()['board_id']  # same live board

    client.delete(f'/v1/taste/profiles/{pid}/share')
    assert client.get(f'/v1/taste/shared/{token}').status_code == 404
    assert client.post(f'/v1/taste/shared/{token}/chat', json={'messages': [{'role': 'user', 'text': 'a scarf'}]}).status_code == 404


def test_gift_chat_searches_with_their_taste_but_not_their_budget_or_bank(client):
    pid = owner(client)
    token = client.post(f'/v1/taste/profiles/{pid}/share').json()['token']
    out = client.post(f'/v1/taste/shared/{token}/chat', json={'messages': [{'role': 'user', 'text': 'a black top'}]}).json()
    assert out['action'] == 'search' and out['budget'] is None and 'size' not in out
    request = client.app.state.budgets.store  # same SQLite store as the jobs
    import json
    with request.connect() as db:
        saved = json.loads(db.execute('SELECT request FROM jobs WHERE id=?', (out['search_id'],)).fetchone()[0])
    assert saved['profile_id'] == pid and saved['for_friend'] is True
    assert saved['request']['max_item_price'] == 10000  # not Maya's own $60 budget
    # A gift search is never recorded against the friend's (mock) bank.
    import time
    for _ in range(100):
        job = client.get(out['status_url']).json()
        if job['status'] in ('completed', 'partial', 'failed'):
            break
        time.sleep(0.05)
    assert job['results']
    bought = client.post('/v1/checkout/mark-bought', json={'search_id': out['search_id'], 'listing_id': job['results'][0]['id']})
    assert bought.status_code == 403


def test_gift_mode_tells_the_agent_who_it_shops_for():
    import asyncio
    from taste.chat import ChatTurn, ShopAgent
    from taste.models import Profile
    seen = {}

    class FakeModel:
        async def call(self, system, content, job_id, stage, max_tokens, schema=None, effort=None):
            seen['system'] = system
            return {'reply': 'Maya would love these.', 'action': 'reply', 'brief': '', 'max_item_price': None,
                    'size': None, 'must_have': [], 'brands': [], 'category': 'other', 'recall': []}

    agent = ShopAgent(Settings(taste_mode='live', anthropic_api_key='k'), FakeModel())
    asyncio.run(agent.respond(Profile(id='p', prompt='quiet luxury'), [ChatTurn(role='user', text='a gift')], recipient='Maya'))
    assert 'GIFT MODE' in seen['system'] and 'their size' in seen['system'] and 'Maya' in seen['system']
