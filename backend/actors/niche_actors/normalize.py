"""Turn each scraper's row into one common listing shape.

Every function returns a dict or None. None means the row is unusable (no https link, title or price),
never a guess. Field names match backend/sourcing/models.py Listing so the backend can validate rows as-is.
"""
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit

from . import retailers

DOMAINS = {'depop': 'depop.com', 'poshmark': 'poshmark.com', 'vinted': 'vinted.com', 'etsy': 'etsy.com',
           'grailed': 'grailed.com'}


def https_url(value, domain=None):
    if not isinstance(value, str):
        return None
    p = urlsplit(value)
    host = (p.hostname or '').lower()
    if p.scheme != 'https' or not host or p.username or p.password:
        return None
    if domain and not (host == domain or host.endswith('.' + domain)):
        return None
    return urlunsplit((p.scheme, p.netloc, p.path, p.query, ''))


def money(value):
    if isinstance(value, dict):
        value = value.get('amount')
    if isinstance(value, str):
        value = value.replace('$', '').replace(',', '').strip()
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value < 10_000_000 else None


def listing(marketplace, ident, *, title, url, price, currency, retailer, tier, image_urls=(), sizes=(),
            condition=None, brand=None, seller=None, available=None, is_ad=None, shipping_cost=None, description='',
            seller_rating=None, seller_reviews=None):
    if not (url and title and price is not None and isinstance(currency, str) and len(currency) == 3):
        return None
    if ident is None:
        ident = hashlib.sha256(url.encode()).hexdigest()[:20]
    return {
        'id': f'{marketplace}:{ident}', 'marketplace': marketplace, 'retailer': retailer, 'tier': tier,
        'title': str(title)[:500], 'url': url, 'price': price, 'currency': currency.upper(),
        'image_urls': [x for x in map(https_url, image_urls) if x][:4], 'sizes': [str(x) for x in sizes if x],
        'condition': condition, 'brand': brand or None, 'seller': seller or None, 'available': available,
        'is_ad': is_ad, 'shipping_cost': shipping_cost, 'description': str(description or '')[:2500],
        # Seller's average review (0-5) and review count, where the marketplace gives them (Etsy shops; Depop sometimes).
        'seller_rating': stars(seller_rating), 'seller_reviews': count(seller_reviews),
    }


def squash(text):
    return re.sub(r'[^a-z0-9]', '', str(text or '').lower())


def stars(value):
    value = money(value)
    return value if value is not None and value <= 5 else None


def count(value):
    value = money(value)
    return int(value) if value is not None else None


def google_shopping(row, include_unlisted=False, brands=()):
    """burbn/google-shopping-scraper. Keeps only stores in the retailer bank unless include_unlisted, plus a brand's own
    store when the shopper named that brand ("like Lewkin" keeps lewkin's listings)."""
    store = row.get('store_name')
    known = retailers.lookup(store)
    asked = any(b and b in squash(store) for b in map(squash, brands))
    if not known and not include_unlisted and not asked:
        return None
    name, tier = known or (store, 'brand' if asked else 'small_shop')
    photos = row.get('product_photos') or []
    return listing('google_shopping', row.get('product_id'), title=row.get('product_title'),
        url=https_url(row.get('product_page_url')), price=money(row.get('price')), currency='USD',
        retailer=name, tier=tier, image_urls=photos if isinstance(photos, list) else [photos],
        condition='new', seller=name, available=True, is_ad=False, description=row.get('shipping') or '')


def depop(row):
    """abotapi/depop-scraper (search mode)."""
    if row.get('isSold') or row.get('isOnSale') is False:
        return None
    sizes = [s.get('name') for s in row.get('sizes') or [] if isinstance(s, dict)]
    return listing('depop', row.get('id'), title=row.get('title') or row.get('description', '')[:120],
        url=https_url(row.get('url'), DOMAINS['depop']), price=money(row.get('price')), currency=row.get('currency'),
        retailer='Depop', tier='resale', image_urls=row.get('pictures') or [row.get('mainPicture')], sizes=sizes,
        condition=row.get('conditionName'), brand=row.get('brandName'), seller=row.get('sellerUsername'),
        available=True, is_ad=bool(row.get('isBoosted')), shipping_cost=money(row.get('shippingCost')),
        description=row.get('description'), seller_rating=row.get('sellerReviewsRating'),
        seller_reviews=row.get('sellerReviewsTotal'))


def poshmark(row):
    """piotrv1001/poshmark-listings-scraper."""
    if row.get('isSold'):
        return None
    url = https_url(row.get('link'), DOMAINS['poshmark'])
    return listing('poshmark', url.rstrip('/').rsplit('-', 1)[-1] if url else None, title=row.get('title'), url=url,
        price=money(row.get('priceValue', row.get('price'))), currency=row.get('currency') or 'USD',
        retailer='Poshmark', tier='resale', image_urls=[row.get('image')], sizes=[row.get('size')],
        condition=None, brand=row.get('brand'), available=True)


def vinted(row):
    """epicscrapers/vinted-search-scraper."""
    price = row.get('price') or {}
    photo = row.get('photo') or {}
    user = row.get('user') if isinstance(row.get('user'), dict) else {}
    return listing('vinted', row.get('id'), title=row.get('title'), url=https_url(row.get('url'), DOMAINS['vinted']),
        price=money(price), currency=price.get('currency_code') if isinstance(price, dict) else None,
        retailer='Vinted', tier='resale', image_urls=[photo.get('full_size_url') or photo.get('url')],
        sizes=[row.get('size_title')], condition=row.get('status'), brand=row.get('brand_title'),
        seller=user.get('login'), available=True, is_ad=bool(row.get('promoted')))


def etsy(row):
    """one_dollar_store/etsy-listings-scraper."""
    return listing('etsy', row.get('listingId'), title=row.get('title'), url=https_url(row.get('url'), DOMAINS['etsy']),
        price=money(row.get('price')), currency=row.get('currency'), retailer='Etsy', tier='small_shop',
        image_urls=[row.get('imageUrl')], seller=row.get('shopName'), is_ad=row.get('isAd'),
        seller_rating=row.get('shopRating'), seller_reviews=row.get('shopReviewCount'))


def grailed(row):
    """devilscrapes/grailed-listings-scraper (documented shape; not yet run live)."""
    if row.get('sold') or row.get('recordType', 'listing') != 'listing':
        return None
    seller = row.get('seller_username') or row.get('seller')
    return listing('grailed', row.get('listing_id') or row.get('id'), title=row.get('title'),
        url=https_url(row.get('listing_url') or row.get('url'), DOMAINS['grailed']), price=money(row.get('price')),
        currency=row.get('currency') or 'USD', retailer='Grailed', tier='resale',
        image_urls=[row.get('image_url') or row.get('coverImageUrl')], sizes=[row.get('size')],
        condition=row.get('condition'), brand=row.get('designer') or row.get('brand'),
        seller=seller.get('username') if isinstance(seller, dict) else seller)
