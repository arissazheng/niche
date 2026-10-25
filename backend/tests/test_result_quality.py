"""Search result quality: sizes in the shopper's own chart, no single taste trait filling the page, and one piece
cross-listed on two marketplaces shown once."""
import io
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
from sourcing import dedupe, sizes
from sourcing.models import Listing, SearchRequest
from sourcing.pipeline import RELEVANT, diversify, eligible, lexical_score, size_adjusted


@pytest.fixture
def request_data():
    return SearchRequest.model_validate_json(Path('examples/search.json').read_text())


def item(ident, score=80, source='etsy', **extra):
    return Listing(id=ident, source=source, title=extra.pop('title', 'black wool coat'), url=f'https://x.invalid/{ident}',
                   price=extra.pop('price', 50), currency='USD', scraped_at='now', score=score,
                   seller=extra.pop('seller', ident), **extra)


def test_numbered_sizes_compare_only_within_one_countrys_chart():
    assert sizes.match('8', ['UK 8']) is None  # a UK 8 is not a US 8: unverified, never a match
    assert sizes.match('8', ['US 8']) and sizes.match('8', ['8'])
    assert sizes.match('UK 10', ['10 UK']) and sizes.match('UK 10', ['US 6 (UK 10)'])
    assert sizes.match('UK 10', ['UK 12']) is False
    assert sizes.match('EU 38', ['EU 38/40']) and sizes.match('EU 38', ['EU 36']) is False
    assert sizes.match('M', ['S']) is False and sizes.match('M', ['UK 10']) is None


def test_title_sizes_are_read_when_the_size_field_is_empty():
    assert sizes.listing_labels([], 'Levis 501 jeans W28') == ['W28']
    assert sizes.listing_labels([], 'Silk slip dress size 8') == ['8']
    assert sizes.listing_labels([], 'Leather boots UK 5') == ['UK 5']
    assert sizes.listing_labels([], 'Cool 90s top') == []


def test_wrong_country_size_is_filtered_and_unknown_size_ranks_lower(request_data):
    request_data.request.size = 'UK 10'
    fits, wrong, unknown = (item('fits', sizes=['UK 10']), item('wrong', sizes=['UK 14']), item('unknown'))
    kept = eligible([fits, wrong, unknown], request_data)
    assert fits in kept and unknown in kept and wrong not in kept
    assert lexical_score(unknown, request_data) < lexical_score(fits, request_data)
    unknown.score = 90
    assert size_adjusted(unknown, request_data) == 75
    unknown.score = 45
    assert size_adjusted(unknown, request_data) == RELEVANT  # never dropped for an unstated size alone
    assert size_adjusted(fits, request_data) == 80


def test_one_taste_trait_cant_fill_the_page(request_data):
    request_data.taste_profile.patterns = ['stripes', 'striped', 'breton stripe']
    request_data.request.query = 'summer top'
    striped = [item(f's{i}', 95 - i, title=f'Striped cotton top {i}') for i in range(10)]
    plain = [item(f'p{i}', 60 - i, title=f'Linen top {i}') for i in range(10)]
    shown = diversify(striped + plain, 10, request_data)
    assert len(shown) == 10 and sum('Striped' in x.title for x in shown) == 4
    request_data.request.query = 'striped top'  # asked for: no cap
    assert sum('Striped' in x.title for x in diversify(striped + plain, 10, request_data)) == 10
    # Three names for one trait count once in the keyword score.
    request_data.taste_profile.colors = request_data.taste_profile.silhouettes = []
    one = item('one', title='striped top', description='breton stripe, stripes')
    assert lexical_score(one, request_data) == lexical_score(item('two', title='striped top'), request_data)


def photo(shift=0, size=400, colour='navy'):
    edge = 400
    image = Image.new('RGB', (edge, edge), 'white')
    draw = ImageDraw.Draw(image)
    for y in range(0, edge, 40):
        draw.rectangle((0, y + shift, edge, y + shift + 20), fill=colour)
    draw.ellipse((edge // 4, edge // 4, edge * 3 // 4, edge * 3 // 4), fill='red')
    out = io.BytesIO()
    image.resize((size, size)).save(out, format='JPEG', quality=70)
    return out.getvalue()


def test_photo_hash_matches_resized_copies_not_other_photos():
    original = dedupe.image_hash(photo())
    resized = dedupe.image_hash(photo(size=250))
    other = dedupe.image_hash(photo(shift=20, colour='green'))
    distance = lambda a, b: bin(int(a, 16) ^ int(b, 16)).count('1')
    assert distance(original, resized) <= dedupe.SAME_PHOTO < dedupe.DIFFERENT_PHOTO < distance(original, other)


def test_a_sellers_cross_listing_shows_once_as_the_better_listing():
    etsy = item('etsy:1', 82, 'etsy', title='Vintage navy striped linen shirt boxy fit', seller='lunavintage', price=60)
    depop = item('depop:1', 80, 'depop', title='navy striped linen shirt boxy fit vintage', seller='luna_vintage_', price=52)
    other = item('depop:2', 70, 'depop', title='Cream cotton cardigan', seller='luna_vintage_')
    shown = diversify([etsy, depop, other], 10)
    assert [x.id for x in shown] == ['depop:1', 'depop:2']  # about as good a fit, and cheaper
    assert shown[0].copies == 2 and shown[1].copies == 1


def test_lookalike_pieces_are_not_merged():
    a = item('a', title='Levis 501 jeans', seller='denimdan', sizes=['W28'])
    b = item('b', title='Levis 501 jeans', seller='denimdan', sizes=['W30'])
    assert len(diversify([a, b], 10)) == 2  # same seller and title, other sizes: two pieces
    c, d = item('c', title='Navy striped linen shirt'), item('d', title='Navy striped linen shirt')
    c.image_hash, d.image_hash = 'f0f0f0f0f0f0f0f0', '0f0f0f0f0f0f0f0f'
    assert len(diversify([c, d], 10)) == 2  # different sellers, different photos
    d.image_hash = 'f0f0f0f0f0f0f0f1'
    assert len(diversify([c, d], 10)) == 1  # the same photo and title, reposted by another account


def test_learned_picks_reach_search_as_a_few_light_hints():
    from taste.models import Profile
    notes = [f'Shortlisted “Striped shirt {i}” (searching “top”): unlike most results it was striped.' for i in range(5)]
    notes.append('Loved “Wool coat”: it was wool.')
    summary = Profile(id='p', prompt='Relaxed earthy basics.', learned_notes=notes).to_sourcing().summary
    assert 'Light hints' in summary and 'Striped shirt' not in summary
    assert summary.count('it was striped') == 1 and 'it was wool' in summary
