import json
import sqlite3
from fastapi.testclient import TestClient
from app import create_app
from sourcing.config import Settings
from taste.fit import effective_sizes, suggest
from taste.models import Measurements, Sizes
from tests.test_taste import png


def test_measurements_point_to_standard_sizes():
    s = suggest(Measurements(bust=36, waist=28, hips=38, inseam=31))
    assert (s.top, s.bottom, s.bottom_length) == ('M', '8', 'regular')
    # The bigger of waist and hips decides the pants size.
    assert suggest(Measurements(waist=25, hips=39)).bottom == '10'
    # Centimetres convert; petite and tall inseams.
    s = suggest(Measurements(unit='cm', bust=81, waist=60, inseam=72))
    assert (s.top, s.bottom, s.bottom_length) == ('XS', '00', 'short')
    assert suggest(Measurements(inseam=34)).bottom_length == 'long'
    assert suggest(Measurements(waist=40, hips=50)).bottom == '22'  # plus sizes
    assert suggest(Measurements(shoulder=15, arm=23)) == Sizes()  # nothing to size from


def test_picked_sizes_win_over_measurements():
    picked = Sizes(top='S', bottom=None)
    filled = effective_sizes(picked, Measurements(bust=40, waist=30, hips=40))
    assert filled.top == 'S' and filled.bottom == '12'


def test_measurements_reach_the_search_but_not_the_taste_profile(tmp_path):
    settings = Settings(database_path=str(tmp_path / 'f.sqlite'), upload_dir=str(tmp_path / 'up'))
    with TestClient(create_app(settings)) as client:
        preview = client.post('/v1/taste/sizes/suggest', json={'unit': 'cm', 'bust': 91, 'inseam': 84})
        assert preview.json()['top'] == 'M' and preview.json()['bottom_length'] == 'long'
        pid = client.post('/v1/taste/profiles', json={'measurements': {'waist': 30, 'hips': 40, 'inseam': 28}}).json()['profile']['id']
        client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
        built = client.post(f'/v1/taste/profiles/{pid}/build').json()['profile']
        assert '30' not in built['prompt']
        reply = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'wide leg jeans'}]}).json()
        assert (reply['size'], reply['length']) == ('12', 'short')
        job = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'jeans'}).json()
        with sqlite3.connect(settings.database_path) as db:
            request = json.loads(db.execute('SELECT request FROM jobs WHERE id=?', (job['search_id'],)).fetchone()[0])
        assert request['request']['measurements'] == {'waist': 30.0, 'hips': 40.0, 'inseam': 28.0}


def test_accessories_are_their_own_category_and_carry_no_size():
    from taste.chat import guess_category
    for text in ('gold hoop earrings', 'black leather crossbody', 'wool beanie', 'chunky silver jewelry', 'straw tote'):
        assert guess_category(text) == 'accessory', text


def test_shoe_size_system_and_letter_bottoms_reach_the_search(tmp_path):
    settings = Settings(database_path=str(tmp_path / 's.sqlite'), upload_dir=str(tmp_path / 'up'))
    with TestClient(create_app(settings)) as client:
        sizes = {'bottom': 'XXS', 'shoe': '8.5', 'shoe_system': 'womens'}
        pid = client.post('/v1/taste/profiles', json={'sizes': sizes}).json()['profile']['id']
        client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
        client.post(f'/v1/taste/profiles/{pid}/build')
        boots = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'black ankle boots'}]}).json()
        bag = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'small shoulder bag'}]}).json()
        skirt = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'slip skirt'}]}).json()
        assert (boots['size'], boots['shoe_size_system']) == ('8.5', 'womens')
        assert (bag['category'], bag['size'], bag['shoe_size_system']) == ('accessory', None, None)
        assert skirt['size'] == 'XXS'
