import json
import sqlite3
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app import create_app
from sourcing.config import Settings
from taste.fit import suggest
from taste.models import Measurements, Onboarding
from taste.sizing import CATALOG, Sizing, for_search, summary
from tests.test_taste import png


def client_for(tmp_path):
    return TestClient(create_app(Settings(database_path=str(tmp_path / 'f.sqlite'), upload_dir=str(tmp_path / 'up'))))


def test_measurements_point_to_sizes_in_each_system():
    w = suggest(Measurements(bust=36, waist=28, hips=38, inseam=31))
    assert (w.tops.values, w.bottoms.values, w.bottoms.extras, w.dresses.values) == (['M'], ['8'], {'inseam': '31'}, ['8'])
    assert suggest(Measurements(waist=25, hips=39)).bottoms.values == ['10']  # the bigger of waist and hips decides
    assert suggest(Measurements(unit='cm', bust=81, waist=60)).tops.values == ['XS']
    m = suggest(Measurements(bust=41, waist=32.4, inseam=30), 'mens')
    assert (m.tops.values, m.bottoms.format, m.bottoms.values, m.bottoms.extras) == (['L'], 'waist', ['32'], {'inseam': '30'})
    assert suggest(Measurements(shoulder=15, arm=23)).tops.values == []  # nothing to size from


def test_sizing_is_checked_against_the_catalog():
    ok = Sizing(system='mens', mens={'bottoms': {'format': 'waist', 'values': ['31', '33'], 'extras': {'inseam': '29'}},
                                     'outerwear': {'format': 'chest', 'values': ['40'], 'extras': {'length': 'R'}},
                                     'shoes': {'format': 'us', 'values': ['10.5'], 'extras': {'width': 'Wide'}}},
                accessories={'rings': {'format': 'us', 'values': ['6.5']}, 'belts': {'format': 'in', 'values': ['32'],
                                                                                  'extras': {'measures': 'Belt length'}}})
    assert ok.mens.bottoms.values == ['31', '33']
    for bad in ({'womens': {'tops': {'format': 'alpha', 'values': ['4XL']}}},     # men's-only size
                {'mens': {'shoes': {'format': 'us', 'values': ['3']}}},           # below the men's US chart
                {'womens': {'bottoms': {'format': 'waist', 'values': ['70']}}},   # typed, but out of range
                {'mens': {'tops': {'format': 'alpha', 'values': ['M'], 'extras': {'fit': 'Tall'}}}}):  # not a tops option
        with pytest.raises(ValidationError):
            Sizing(**bad)
    bra = Sizing(womens={'bra': {'band': '34', 'cup': 'DD'}}).womens.bra
    assert bra.size == '34DD'


def test_switching_systems_keeps_both_sets_and_accessories():
    s = Sizing(system='womens', womens={'tops': {'format': 'alpha', 'values': ['S']}},
               mens={'tops': {'format': 'alpha', 'values': ['M']}}, accessories={'hats': {'format': 'alpha', 'values': ['M']}})
    assert s.active().tops.values == ['S']
    s.system = 'mens'
    assert s.active().tops.values == ['M'] and s.accessories.hats.values == ['M']


def test_old_flat_sizes_are_upgraded():
    ob = Onboarding.model_validate({'sizes': {'top': 'S', 'bottom': '8', 'bottom_length': 'long', 'shoe': '8.5',
                                              'shoe_system': 'womens', 'outerwear': None}})
    w = ob.sizing.womens
    assert ob.sizing.system == 'womens' and (w.tops.values, w.bottoms.values, w.shoes.values) == (['S'], ['8'], ['8.5'])
    assert w.dresses.extras == {'fit': 'Tall'}
    assert Onboarding.model_validate({'sizes': {'bottom': '36'}}).sizing.womens.bottoms.values == []  # not in the chart


def test_search_gets_size_filter_note_length_and_shoe_chart():
    s = Sizing(system='mens', mens={'bottoms': {'format': 'waist', 'values': ['32'], 'extras': {'inseam': '34'}},
                                    'shoes': {'format': 'eu', 'values': ['43']}},
               accessories={'rings': {'format': 'us', 'values': ['9']}})
    pants = for_search(s, 'bottom')
    assert pants['size'] == '32' and pants['length'] == 'long' and pants['size_note'] == "Bottoms: 32 (Waist (in)), inseam 34 in (men's chart)"
    shoes = for_search(s, 'shoes')
    # EU sizes filter with the country named, so a US 43 or UK 43 never passes for it.
    assert shoes['size'] == 'EU 43' and shoes['shoe_size_system'] is None and 'EU' in shoes['size_note']
    assert for_search(s, 'accessory', 'silver signet ring')['size'] == '9'
    assert for_search(s, 'accessory', 'leather tote')['size'] is None
    assert for_search(Sizing(womens={'dresses': {'format': 'us', 'values': ['4'], 'extras': {'fit': 'Petite'}}}), 'dress')['length'] == 'short'
    assert 'Rings: 9' in summary(s)


def test_catalog_and_sizes_flow_through_the_api(tmp_path):
    with client_for(tmp_path) as client:
        catalog = client.get('/v1/taste/sizing/catalog').json()
        assert 'bra' in catalog and 'bra' not in catalog['mens'] and catalog['mens']['dresses']['optional']
        assert catalog['womens']['shoes']['formats'][0]['options'][0] == '4' and catalog['mens']['shoes']['formats'][0]['options'][0] == '5'
        preview = client.post('/v1/taste/sizes/suggest?system=mens', json={'bust': 44}).json()
        assert preview['tops']['values'] == ['L']
        sizing = {'system': 'womens', 'womens': {'bottoms': {'format': 'us', 'values': ['6', '8']},
                                                  'shoes': {'format': 'us', 'values': ['8.5']}}}
        pid = client.post('/v1/taste/profiles', json={'data_consent': True, 'sizing': sizing,
                                                      'measurements': {'bust': 35}}).json()['profile']['id']
        client.post(f'/v1/taste/profiles/{pid}/images', files={'file': ('a.png', png((20, 20, 20)))})
        client.post(f'/v1/taste/profiles/{pid}/build')
        jeans = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'wide leg jeans'}]}).json()
        boots = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'black ankle boots'}]}).json()
        tee = client.post(f'/v1/taste/profiles/{pid}/chat', json={'messages': [{'role': 'user', 'text': 'white tee'}]}).json()
        assert jeans['size'] == '6/8' and (boots['size'], boots['shoe_size_system']) == ('8.5', 'womens')
        assert tee['size'] == 'S'  # not picked, so from the measured bust
        job = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'jeans', 'size': '6/8', 'size_note': 'Bottoms: 6 or 8'}).json()
        with sqlite3.connect(tmp_path / 'f.sqlite') as db:
            request = json.loads(db.execute('SELECT request FROM jobs WHERE id=?', (job['search_id'],)).fetchone()[0])
        assert request['request']['size_note'] == 'Bottoms: 6 or 8' and request['request']['measurements'] == {'bust': 35.0}
        job = client.post(f'/v1/taste/profiles/{pid}/searches', json={'query': 'white tee'}).json()
        with sqlite3.connect(tmp_path / 'f.sqlite') as db:
            request = json.loads(db.execute('SELECT request FROM jobs WHERE id=?', (job['search_id'],)).fetchone()[0])
        assert request['request']['size'] == 'S'



def test_size_regions_have_their_own_charts_and_us_is_the_default():
    assert Sizing().region == 'us' and [r['id'] for r in CATALOG['regions']] == ['us', 'uk', 'eu', 'asia']
    uk = Sizing(region='uk', womens={'dresses': {'format': 'uk', 'values': ['12']},
                                      'bra': {'notation': 'uk', 'band': '34', 'cup': 'FF'}})
    assert uk.womens.bra.size == '34FF'
    with pytest.raises(ValidationError):  # FF is a UK cup, not a US one
        Sizing(womens={'bra': {'notation': 'us', 'band': '34', 'cup': 'FF'}})
    eu = Sizing(region='eu', system='mens', mens={'bottoms': {'format': 'eu', 'values': ['50'], 'extras': {'inseam_cm': '81'}},
                                                  'outerwear': {'format': 'eu', 'values': ['50'], 'extras': {'length': 'L'}}})
    pants = for_search(eu, 'bottom')
    assert pants['size'] == 'EU 50' and pants['length'] == 'regular' and 'EU numeric' in pants['size_note']  # 81 cm ≈ 32 in
    assert for_search(uk, 'dress')['size'] == 'UK 12'  # filtered in the UK chart, not as a US 12
    bra = for_search(uk, 'bra')
    assert bra['size'] is None and bra['size_note'] == 'Bra 34FF (UK band and cup)'  # only US cups filter listings
    jp_ring = Sizing(region='asia', accessories={'rings': {'format': 'jp', 'values': ['11']}})
    assert 'Japan' in for_search(jp_ring, 'accessory', 'silver ring')['size_note']
