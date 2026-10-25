"""One piece listed more than once: a seller cross-posting the same item on Etsy and Depop (or any two sources), or
re-posting it on one marketplace. Only the better listing is shown; `copies` counts the rest.

Listings are the same piece when the seller matches and either the photos are near identical or the titles mostly
agree, or, from different sellers, when both the photo and the title match. Listings in different sizes never are.
Photos are compared by a small difference hash taken when the ranker downloads them (Listing.image_hash), so no extra
downloads are made.
"""
import io
import re
from PIL import Image
from . import sizes

HASH_EDGE = 8
SAME_PHOTO = 10  # bits out of 64: resized or recompressed copies of one photo
NEAR_IDENTICAL_PHOTO = 4  # strangers' listings must share the photo itself
DIFFERENT_PHOTO = 20  # clearly other photos: two pieces, however alike the titles
SAME_TITLE = 0.7  # share of title words in common
SIMILAR_TITLE = 0.5  # enough alongside the same photo
STOP = {'the', 'and', 'with', 'for', 'size', 'new', 'nwt', 'nwot', 'womens', 'women', 'mens', 'men', 'unisex',
        'vintage', 'free', 'shipping'}


def image_hash(data: bytes) -> str | None:
    """64-bit difference hash of a photo, as hex."""
    try:
        image = Image.open(io.BytesIO(data)).convert('L').resize((HASH_EDGE + 1, HASH_EDGE))
    except (OSError, ValueError):
        return None
    pixels = list(image.tobytes())
    bits = 0
    for row in range(HASH_EDGE):
        for col in range(HASH_EDGE):
            left, right = pixels[row * (HASH_EDGE + 1) + col], pixels[row * (HASH_EDGE + 1) + col + 1]
            bits = bits << 1 | (left > right)
    return f'{bits:016x}'


def photo_distance(a, b):
    if not a.image_hash or not b.image_hash:
        return None
    return bin(int(a.image_hash, 16) ^ int(b.image_hash, 16)).count('1')


def title_words(title):
    return {w.rstrip('s') for w in re.findall(r'[a-z0-9]+', title.lower()) if len(w) > 1 and w not in STOP}


def title_overlap(a, b):
    x, y = title_words(a.title), title_words(b.title)
    return len(x & y) / len(x | y) if x and y else 0


def seller_key(item):
    return re.sub(r'[^a-z0-9]', '', (item.seller or '').lower())


def same_seller(a, b):
    x, y = seller_key(a), seller_key(b)
    # Handles differ a little across marketplaces ("lunavintage" on Etsy, "luna_vintage_" on Depop).
    return bool(x and y) and (x == y or (min(len(x), len(y)) >= 5 and (x in y or y in x)))


def distinct(a, b):
    """Clearly two pieces, however alike the listings read: other sizes, or other photos."""
    x, y = (set().union(*(sizes.tokens(s) for s in item.sizes)) if item.sizes else set() for item in (a, b))
    photos = photo_distance(a, b)
    return (bool(x and y) and not x & y) or (photos is not None and photos > DIFFERENT_PHOTO)


def same_piece(a, b):
    if distinct(a, b):
        return False
    photos = photo_distance(a, b)
    titles = title_overlap(a, b)
    if same_seller(a, b):
        return titles >= SAME_TITLE or (photos is not None and photos <= SAME_PHOTO)
    return photos is not None and photos <= NEAR_IDENTICAL_PHOTO and titles >= SIMILAR_TITLE


def better(a, b):
    """The listing to show: the better fit, or when the fit is about the same, the cheaper one delivered."""
    if abs((a.score or 0) - (b.score or 0)) > 5:
        return a if (a.score or 0) > (b.score or 0) else b
    cost = lambda x: x.price + (x.shipping_cost or 0)
    if cost(a) != cost(b):
        return a if cost(a) < cost(b) else b
    return a if (a.seller_reviews or 0) >= (b.seller_reviews or 0) else b


def collapse(items, same=same_piece):
    """One listing per piece, best first by score. Each kept listing's `copies` counts the listings it stands for."""
    groups = []
    for item in items:
        for group in groups:
            if any(same(item, x) for x in group):
                group.append(item)
                break
        else:
            groups.append([item])
    kept = []
    for group in groups:
        best = group[0]
        for other in group[1:]:
            best = better(best, other)
        best.copies = len(group)
        kept.append(best)
    return sorted(kept, key=lambda x: x.score or 0, reverse=True)
