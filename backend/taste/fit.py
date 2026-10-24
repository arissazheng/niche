"""Turning optional body measurements into sizes, using a standard US women's size chart.

Charts differ by brand, so these are starting points: a size the shopper picked always wins, and the raw measurements
also go to the ranker, which compares them with garment measurements that many secondhand listings state.
Measurements never go into the taste profile.
"""
from .models import Measurements, Sizes

# Letter sizes by bust, in inches (upper bound of each size).
TOP_BY_BUST = [(33.5, 'XS'), (35.5, 'S'), (37.5, 'M'), (40.5, 'L'), (43.5, 'XL')]
# US numbered sizes by (waist, hips) in inches: misses 00-16, then plus sizes in 2-inch steps up to 40.
NUMBERED = [('00', 23.5, 33.5), ('0', 24.5, 34.5), ('2', 25.5, 35.5), ('4', 26.5, 36.5), ('6', 27.5, 37.5),
            ('8', 28.5, 38.5), ('10', 29.5, 39.5), ('12', 31, 41), ('14', 32.5, 42.5), ('16', 34, 44)]
NUMBERED += [(str(n), 34 + (n - 16), 44 + (n - 16)) for n in range(18, 41, 2)]
# Inseam: petite at 29 in or under, tall at 32.5 in or over.
SHORT_INSEAM, LONG_INSEAM = 29, 32.5


def inches(m: Measurements) -> dict[str, float]:
    """The measurements given, converted to inches (rounded to a quarter inch)."""
    factor = 1 / 2.54 if m.unit == 'cm' else 1
    values = m.model_dump(exclude={'unit'}, exclude_none=True)
    return {k: round(v * factor * 4) / 4 for k, v in values.items()}


def top_size(bust):
    return next((size for limit, size in TOP_BY_BUST if bust <= limit), 'XXL')


def numbered_size(waist=None, hips=None):
    """The smallest size that fits both waist and hips (fit the larger of the two)."""
    for size, max_waist, max_hips in NUMBERED:
        if (waist is None or waist <= max_waist) and (hips is None or hips <= max_hips):
            return size
    return NUMBERED[-1][0]


def suggest(m: Measurements) -> Sizes:
    """Sizes the measurements point to; fields with no measurement behind them stay empty."""
    body = inches(m)
    top = top_size(body['bust']) if 'bust' in body else None
    bottom = numbered_size(body.get('waist'), body.get('hips')) if {'waist', 'hips'} & body.keys() else None
    length = None
    if 'inseam' in body:
        length = 'short' if body['inseam'] <= SHORT_INSEAM else 'long' if body['inseam'] >= LONG_INSEAM else 'regular'
    return Sizes(top=top, bottom=bottom, bottom_length=length, outerwear=top)


def effective_sizes(sizes: Sizes, m: Measurements) -> Sizes:
    """The shopper's picked sizes, with gaps filled from their measurements."""
    suggested = suggest(m)
    return Sizes(**{k: getattr(sizes, k) if getattr(sizes, k) is not None else getattr(suggested, k, None)
                    for k in Sizes.model_fields})
