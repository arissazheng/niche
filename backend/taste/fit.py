"""Turning optional body measurements into sizes, using standard US size charts.

Charts differ by brand, so these are starting points: a size the shopper picked always wins, and the raw measurements
also go to the ranker, which compares them with garment measurements that many secondhand listings state.
Measurements never go into the taste profile.
"""
from .models import Measurements
from .sizing import ClothingSizes, Pick, System

# Women's letter sizes by bust, men's by chest, in inches (upper bound of each size).
WOMENS_TOP = [(33.5, 'XS'), (35.5, 'S'), (37.5, 'M'), (40.5, 'L'), (43.5, 'XL'), (46.5, 'XXL'), (49.5, '1X'), (52.5, '2X')]
MENS_TOP = [(34.5, 'XS'), (37.5, 'S'), (40.5, 'M'), (44.5, 'L'), (48.5, 'XL'), (52.5, 'XXL'), (56.5, '3XL')]
# Women's US numbered sizes by (waist, hips) in inches: misses 00-16, then plus sizes in 2-inch steps to 24.
NUMBERED = [('00', 23.5, 33.5), ('0', 24.5, 34.5), ('2', 25.5, 35.5), ('4', 26.5, 36.5), ('6', 27.5, 37.5),
            ('8', 28.5, 38.5), ('10', 29.5, 39.5), ('12', 31, 41), ('14', 32.5, 42.5), ('16', 34, 44)]
NUMBERED += [(str(n), 34 + (n - 16), 44 + (n - 16)) for n in range(18, 25, 2)]


def inches(m: Measurements) -> dict[str, float]:
    """The measurements given, converted to inches (rounded to a quarter inch)."""
    factor = 1 / 2.54 if m.unit == 'cm' else 1
    values = m.model_dump(exclude={'unit'}, exclude_none=True)
    return {k: round(v * factor * 4) / 4 for k, v in values.items()}


def top_size(bust, system: System = 'womens'):
    chart = WOMENS_TOP if system == 'womens' else MENS_TOP
    return next((size for limit, size in chart if bust <= limit), '3X' if system == 'womens' else '4XL')


def numbered_size(waist=None, hips=None):
    """The smallest size that fits both waist and hips (fit the larger of the two)."""
    for size, max_waist, max_hips in NUMBERED:
        if (waist is None or waist <= max_waist) and (hips is None or hips <= max_hips):
            return size
    return NUMBERED[-1][0]


def suggest(m: Measurements, system: System = 'womens') -> ClothingSizes:
    """Sizes the measurements point to in this system; categories with no measurement behind them stay empty."""
    body = inches(m)
    out = ClothingSizes()
    if 'bust' in body:
        out.tops = Pick(format='alpha', values=[top_size(body['bust'], system)])
        out.outerwear = Pick(format='alpha', values=out.tops.values)
    inseam = {'inseam': f'{round(body["inseam"]):g}'} if 24 <= body.get('inseam', 0) <= 38 else {}
    if system == 'womens' and {'waist', 'hips'} & body.keys():
        size = numbered_size(body.get('waist'), body.get('hips'))
        out.bottoms = Pick(format='us', values=[size], extras=inseam)
        out.dresses = Pick(format='us', values=[size])
    elif system == 'mens' and 24 <= body.get('waist', 0) <= 54:
        out.bottoms = Pick(format='waist', values=[f'{round(body["waist"]):g}'], extras=inseam)
    elif inseam:
        out.bottoms = Pick(extras=inseam)
    return out
