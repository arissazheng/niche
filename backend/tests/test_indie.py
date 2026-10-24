import asyncio
from actors.niche_actors import indie

SHOP = {'domain': 'shop.example', 'name': 'Example Label', 'currency': 'USD'}


def product(ident, title, price, product_type='Dresses', tags='', available=True, sizes=('XS', 'S')):
    return {'id': ident, 'title': title, 'handle': title.lower().replace(' ', '-'), 'product_type': product_type,
            'vendor': 'Example Label', 'tags': tags, 'body_html': '<p>Cut on the <b>bias</b>.</p>',
            'images': [{'src': f'https://cdn.example/{ident}.jpg'}],
            'options': [{'name': 'Size', 'values': list(sizes)}, {'name': 'Color', 'values': ['Black']}],
            'variants': [{'price': str(price + 20), 'available': False}, {'price': str(price), 'available': available}]}


def test_shopify_product_becomes_a_listing_row():
    row = indie.listing(product(7, 'Satin Midi Dress', 180), SHOP)
    assert row['id'] == 'shopify:shop.example:7' and row['url'] == 'https://shop.example/products/satin-midi-dress'
    assert (row['price'], row['currency'], row['retailer'], row['tier']) == (180, 'USD', 'Example Label', 'small_shop')
    assert row['sizes'] == ['XS', 'S'] and row['image_urls'] == ['https://cdn.example/7.jpg']
    assert row['description'] == 'Cut on the bias .' and row['available'] and row['condition'] == 'new'


def test_matching_needs_the_item_type_and_more_than_a_colour():
    dress, top = product(1, 'Black Satin Midi Dress', 150), product(2, 'Black Satin Cami', 80, 'Tops')
    plain = product(3, 'Black Wrap Dress', 120)
    assert indie.score('black satin midi dress', dress) > indie.score('black satin midi dress', plain) > 0
    assert indie.score('black satin midi dress', top) == 0  # satin and black, but not a dress
    assert indie.score('something black', dress) == 0  # a colour alone isn't a match


def test_run_filters_price_and_stock_and_caps_each_shop(monkeypatch):
    catalog = [product(i, f'Satin Midi Dress {i}', 100 + i) for i in range(6)] + \
              [product(10, 'Satin Midi Dress Luxe', 900), product(11, 'Satin Midi Dress Gone', 90, available=False)]

    async def fake_catalog(clients, shop):
        return catalog
    monkeypatch.setattr(indie, 'catalog', fake_catalog)
    rows, summary = asyncio.run(indie.handle({'queries': ['satin midi dress'], 'maxPrice': 200, 'itemsPerQuery': 10,
                                              'shops': [SHOP]}))
    assert summary['sources'] == {'shop.example': {'status': 'succeeded', 'count': 8}}
    assert len(rows) == indie.PER_SHOP and all(r['price'] <= 200 and r['available'] for r in rows)
