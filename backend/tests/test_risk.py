from sourcing.models import Listing
from sourcing.risk import flag


def item(ident, price, **extra):
    return Listing(id=ident, source='etsy', title=extra.pop('title', 'black wool coat'), url=f'https://www.etsy.com/{ident}',
                   price=price, currency='USD', scraped_at='now', **extra)


def test_flags_cheap_off_platform_and_badly_reviewed_sellers():
    items = flag([item('a', 80), item('b', 90), item('c', 85), item('d', 95),
                  item('cheap', 15), item('venmo', 82, description='DM me to buy, Venmo only'),
                  item('bad', 88, seller_rating=3.2, seller_reviews=41), item('new', 79, seller_reviews=0),
                  item('good', 84, seller_rating=4.9, seller_reviews=300)])
    risks = {x.id: x.risks for x in items}
    assert 'far below' in risks['cheap'][0]
    assert 'outside the marketplace' in risks['venmo'][0]
    assert risks['bad'] == ['Seller rated 3.2/5 from 41 reviews.']
    assert risks['new'] == ['This seller has no reviews yet.']
    assert risks['good'] == [] and risks['a'] == []


def test_no_price_warning_on_small_or_cheap_pages():
    assert flag([item('a', 10), item('b', 3)])[1].risks == []
    assert all(not x.risks for x in flag([item(str(i), p) for i, p in enumerate([8, 9, 10, 12, 2])]))


def test_actor_rows_carry_seller_reviews():
    from actors.niche_actors import normalize
    row = normalize.etsy({'listingId': 1, 'title': 'coat', 'url': 'https://www.etsy.com/listing/1', 'price': 40,
                          'currency': 'USD', 'shopName': 's', 'shopRating': 4.5, 'shopReviewCount': 17})
    assert (row['seller_rating'], row['seller_reviews']) == (4.5, 17)


def test_identical_listings_collapse_to_one_with_a_warning():
    from sourcing.pipeline import diversify
    belts = [item(f'b{i}', 13.5, title='Black pyramid stud belt. Black faux-leather strap') for i in range(6)]
    for i, x in enumerate(belts):
        x.score = 80 - i
    shown = flag(diversify(belts + [item('coat', 90)], 20))
    assert [x.id for x in shown] == ['b0', 'coat']
    assert 'appears 6 times' in shown[0].risks[0] and shown[1].risks == []
