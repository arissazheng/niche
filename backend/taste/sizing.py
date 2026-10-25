"""Size preferences: which size chart a shopper uses, and their sizes in it, per clothing category.

The catalog below is the single source of truth: the onboarding page renders from it (GET /v1/taste/sizing/catalog)
and saved preferences are checked against it. Women's and men's preferences are kept side by side so switching
systems never loses either. The system only decides which charts are shown and how sizes are read; it never
limits what gets recommended. Accessory sizes are shared by both systems.
"""
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

System = Literal['womens', 'mens']


def halves(start, stop, step=0.5):
    out, x = [], start
    while x <= stop + 1e-9:
        out.append(f'{x:g}')
        x += step
    return out


def evens(start, stop):
    return [str(n) for n in range(start, stop + 1, 2)]


W_ALPHA = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', '1X', '2X', '3X']
M_ALPHA = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', '4XL']
ACCESSORY_ALPHA = ['XS', 'S', 'M', 'L', 'XL']
WIDTHS = ['Narrow', 'Standard', 'Wide', 'Extra wide']
# Size regions: which country charts show first. US is the default. Letter sizes and most body measurements
# belong to every region; numbered charts belong to theirs.
REGIONS = [{'id': 'us', 'label': 'US'}, {'id': 'uk', 'label': 'UK'}, {'id': 'eu', 'label': 'EU'},
           {'id': 'asia', 'label': 'Asia (Japan)'}]
Region = Literal['us', 'uk', 'eu', 'asia']
INCHES, CENTIMETRES = ['us', 'uk'], ['eu', 'asia']


def fmt(id, label, options, custom=None, regions=None):
    """A size format. `custom` = (min, max) allows typed values in that range beyond the listed options; `regions`
    limits it to those size regions (none = every region)."""
    return {'id': id, 'label': label, 'options': options, **({'custom': list(custom)} if custom else {}),
            **({'regions': regions} if regions else {})}


def extra(id, label, options, custom=None, formats=None, tucked=None, regions=None):
    """An optional add-on to a category (inseam, fit, width...); `formats` limits it to those formats, `regions` to
    those size regions, and `tucked` names a small link that reveals it, for details few people need."""
    return {'id': id, 'label': label, 'options': options, **({'custom': list(custom)} if custom else {}),
            **({'formats': formats} if formats else {}), **({'tucked': tucked} if tucked else {}),
            **({'regions': regions} if regions else {})}


def womens_numbered():
    """Women's numbered clothing sizes per region (they don't convert one-to-one across brands)."""
    return [fmt('us', 'US numeric', ['00', '0'] + evens(2, 24), regions=['us']),
            fmt('uk', 'UK numeric', evens(4, 28), regions=['uk']),
            fmt('eu', 'EU numeric', evens(30, 56), regions=['eu']),
            fmt('jp', 'Japan numeric', [str(n) for n in range(3, 24, 2)], regions=['asia'])]


def shoes(us, uk, eu, cm):
    # Every shoe chart stays available in any region; the region only picks which opens first.
    return {'label': 'Shoes', 'every_region': True,
            'formats': [fmt('us', 'US', halves(*us), regions=['us']), fmt('uk', 'UK', halves(*uk), regions=['uk']),
                        fmt('eu', 'EU', halves(*eu), regions=['eu']), fmt('cm', 'JP / cm', halves(*cm), regions=['asia'])],
            'extras': [extra('width', 'Width', WIDTHS)]}


TOPS_HINT = 'T-shirts, blouses, shirts, knitwear, sweaters, cardigans, hoodies'
BOTTOMS_HINT = 'Jeans, pants, trousers, shorts'
OUTERWEAR_HINT = 'Jackets, coats, blazers, trench, leather, puffers'
INSEAMS = [extra('inseam', 'Inseam (in)', ['28', '30', '32', '34', '36'], custom=(24, 38), regions=INCHES),
           extra('inseam_cm', 'Inseam (cm)', ['71', '76', '81', '86', '91'], custom=(60, 97), regions=CENTIMETRES)]
CHEST = [fmt('chest', 'Chest (in)', evens(34, 52), (30, 60), regions=INCHES),
         fmt('chest_cm', 'Chest (cm)', [str(n) for n in range(86, 135, 4)], (76, 152), regions=CENTIMETRES)]
DRESS_FIT = extra('fit', 'Fit', ['Petite', 'Regular', 'Tall'])

CATALOG = {
    'regions': REGIONS,
    'womens': {
        'tops': {'label': 'Tops', 'hint': TOPS_HINT, 'formats': [fmt('alpha', 'Letter', W_ALPHA), *womens_numbered()]},
        'bottoms': {'label': 'Bottoms', 'hint': BOTTOMS_HINT,
                    'formats': [*womens_numbered(),
                                fmt('waist', 'Waist (in)', [str(n) for n in range(24, 41)], (22, 50), regions=INCHES),
                                fmt('waist_cm', 'Waist (cm)', [str(n) for n in range(60, 105, 4)], (55, 127), regions=CENTIMETRES),
                                fmt('alpha', 'Letter', W_ALPHA)],
                    'extras': INSEAMS},
        'dresses': {'label': 'Dresses & skirts', 'formats': [*womens_numbered(), fmt('alpha', 'Letter', W_ALPHA)],
                    'extras': [DRESS_FIT]},
        'outerwear': {'label': 'Outerwear', 'hint': OUTERWEAR_HINT,
                      'formats': [fmt('alpha', 'Letter', W_ALPHA), *womens_numbered()]},
        'shoes': shoes((4, 13), (2, 11), (34, 44), (21, 30)),
    },
    'mens': {
        'tops': {'label': 'Tops', 'hint': TOPS_HINT, 'formats': [fmt('alpha', 'Letter', M_ALPHA), *CHEST],
                 'extras': [extra('neck', 'Dress shirt neck (in)', halves(14, 18.5), (13, 22), tucked='Dress shirt neck & sleeve',
                                  regions=INCHES),
                            extra('sleeve', 'Dress shirt sleeve (in)', [str(n) for n in range(32, 38)], (30, 40),
                                  tucked='Dress shirt neck & sleeve', regions=INCHES),
                            extra('neck_cm', 'Dress shirt collar (cm)', [str(n) for n in range(36, 47)], (33, 52),
                                  tucked='Dress shirt collar', regions=CENTIMETRES)]},
        'bottoms': {'label': 'Bottoms', 'hint': BOTTOMS_HINT,
                    'formats': [fmt('waist', 'Waist (in)', [str(n) for n in range(26, 37)] + ['38', '40', '42', '44'], (24, 54),
                                    regions=INCHES),
                                fmt('eu', 'EU numeric', evens(42, 62), regions=['eu']),
                                fmt('waist_cm', 'Waist (cm)', [str(n) for n in range(66, 115, 4)], (60, 140), regions=['asia']),
                                fmt('alpha', 'Letter', M_ALPHA)],
                    'extras': INSEAMS},
        # Not shown by default for men's sizing, but available to add.
        'dresses': {'label': 'Dresses & skirts', 'optional': True,
                    'formats': [*womens_numbered(), fmt('alpha', 'Letter', W_ALPHA)], 'extras': [DRESS_FIT]},
        'outerwear': {'label': 'Outerwear', 'hint': OUTERWEAR_HINT,
                      'formats': [fmt('alpha', 'Letter', M_ALPHA[1:]), CHEST[0],
                                  fmt('eu', 'EU numeric', evens(44, 60), regions=['eu']), CHEST[1] | {'regions': ['asia']}],
                      # Tailoring length (40R, 50L): a suffix on a chest or EU size, not a letter size.
                      'extras': [extra('length', 'Jacket length', ['S', 'R', 'L'], formats=['chest', 'eu'])]},
        'shoes': shoes((5, 16), (4, 15), (38, 50), (23, 33)),
    },
    # Band and cup per region. Cup letters differ by region (a US DDD is not a UK E), so they are never converted.
    'bra': {'label': 'Bra size', 'regions': {
        'us': {'bands': evens(28, 46), 'band_custom': [26, 56],
               'cups': ['AA', 'A', 'B', 'C', 'D', 'DD', 'DDD', 'G', 'H', 'I', 'J'], 'cups_extended': ['K', 'L', 'M', 'N']},
        'uk': {'bands': evens(28, 46), 'band_custom': [26, 56],
               'cups': ['AA', 'A', 'B', 'C', 'D', 'DD', 'E', 'F', 'FF', 'G', 'GG', 'H', 'HH', 'J'], 'cups_extended': ['JJ', 'K', 'KK', 'L']},
        'eu': {'bands': [str(n) for n in range(60, 111, 5)], 'band_custom': [55, 130],
               'cups': ['AA', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'], 'cups_extended': ['K', 'L', 'M', 'N']},
        'asia': {'bands': [str(n) for n in range(60, 111, 5)], 'band_custom': [55, 130],
                 'cups': ['AA', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'], 'cups_extended': ['K', 'L']},
    }},
    'accessories': {
        'belts': {'label': 'Belts',
                  'formats': [fmt('in', 'Inches', evens(26, 46), (20, 60), regions=INCHES),
                              fmt('cm', 'cm', [str(n) for n in range(70, 121, 5)], (50, 150)), fmt('alpha', 'Letter', ACCESSORY_ALPHA)],
                  # A waist measurement and a belt's own length differ (a belt runs a few inches longer).
                  'extras': [extra('measures', 'This number is', ['My waist', 'Belt length'], formats=['in', 'cm'])]},
        'hats': {'label': 'Hats',
                 'formats': [fmt('alpha', 'Letter', ACCESSORY_ALPHA),
                             fmt('fitted', 'US fitted', ['6 3/4', '6 7/8', '7', '7 1/8', '7 1/4', '7 3/8', '7 1/2', '7 5/8', '7 3/4'],
                                 regions=['us']),
                             fmt('cm', 'Head (cm)', [str(n) for n in range(53, 63)], (48, 66))]},
        'gloves': {'label': 'Gloves',
                   'formats': [fmt('alpha', 'Letter', ACCESSORY_ALPHA), fmt('in', 'Hand (in)', halves(6, 10), (5, 12), regions=INCHES),
                               fmt('cm', 'Hand (cm)', [str(n) for n in range(15, 27)], (12, 30))]},
        'rings': {'label': 'Rings',
                  'formats': [fmt('us', 'US', halves(3, 13), (1, 16), regions=['us']),
                              fmt('uk', 'UK', [chr(c) for c in range(ord('F'), ord('Z') + 1)], regions=['uk']),
                              fmt('jp', 'Japan', [str(n) for n in range(1, 28)], regions=['asia']),
                              # EU ring sizes are the finger's circumference in mm.
                              fmt('mm', 'EU / finger (mm)', [str(n) for n in range(44, 72, 2)], (38, 80))]},
    },
}
CLOTHING = ('tops', 'bottoms', 'dresses', 'outerwear', 'shoes')
ACCESSORIES = ('belts', 'hats', 'gloves', 'rings')


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Pick(Strict):
    """Sizes in one category: the chart (`format`), the acceptable sizes in it, and optional extras (inseam, fit...)."""
    format: str | None = None
    values: list[str] = Field(default_factory=list, max_length=8)
    extras: dict[str, str] = Field(default_factory=dict)

    @field_validator('values')
    @classmethod
    def tidy(cls, values):
        return list(dict.fromkeys(v.strip() for v in values if v.strip()))


class Bra(Strict):
    """Band and cup kept separately, in one region's notation, plus the combined size ("34C"). Cup letters are
    never converted between regions."""
    notation: Region = 'us'
    band: str | None = None
    cup: str | None = None
    size: str | None = None

    @model_validator(mode='after')
    def combine(self):
        self.size = f'{self.band}{self.cup}' if self.band and self.cup else None
        return self


class ClothingSizes(Strict):
    tops: Pick = Field(default_factory=Pick)
    bottoms: Pick = Field(default_factory=Pick)
    dresses: Pick = Field(default_factory=Pick)
    outerwear: Pick = Field(default_factory=Pick)
    shoes: Pick = Field(default_factory=Pick)
    bra: Bra = Field(default_factory=Bra)


class AccessorySizes(Strict):
    belts: Pick = Field(default_factory=Pick)
    hats: Pick = Field(default_factory=Pick)
    gloves: Pick = Field(default_factory=Pick)
    rings: Pick = Field(default_factory=Pick)


def _number(value):
    try:
        return float(value)
    except ValueError:
        return None


def _check(pick: Pick, spec: dict, where: str):
    if not pick.format and not pick.values:
        return
    formats = {f['id']: f for f in spec['formats']}
    if pick.format not in formats:
        raise ValueError(f'{where}: unknown size format {pick.format!r}')
    chart = formats[pick.format]
    for value in pick.values:
        typed = _number(value)
        low, high = chart.get('custom', (None, None))
        if value not in chart['options'] and not (low is not None and typed is not None and low <= typed <= high):
            raise ValueError(f'{where}: {value!r} is not a {chart["label"]} size')
    extras = {e['id']: e for e in spec.get('extras', [])}
    for key, value in pick.extras.items():
        if key not in extras:
            raise ValueError(f'{where}: unknown option {key!r}')
        low, high = extras[key].get('custom', (None, None))
        typed = _number(value)
        if value not in extras[key]['options'] and not (low is not None and typed is not None and low <= typed <= high):
            raise ValueError(f'{where}: {value!r} is not a valid {extras[key]["label"]}')


class Sizing(Strict):
    system: System | None = None
    region: Region = 'us'  # which country charts show first
    womens: ClothingSizes = Field(default_factory=ClothingSizes)
    mens: ClothingSizes = Field(default_factory=ClothingSizes)
    accessories: AccessorySizes = Field(default_factory=AccessorySizes)

    @model_validator(mode='after')
    def valid(self):
        for system in ('womens', 'mens'):
            sizes = getattr(self, system)
            for category in CLOTHING:
                _check(getattr(sizes, category), CATALOG[system][category], f'{system} {category}')
        bra = self.womens.bra
        spec = CATALOG['bra']['regions'][bra.notation]
        if bra.band and bra.band not in spec['bands'] and not (
                _number(bra.band) and spec['band_custom'][0] <= _number(bra.band) <= spec['band_custom'][1]):
            raise ValueError(f'bra band {bra.band!r} is not a {bra.notation.upper()} band size')
        if bra.cup and bra.cup not in spec['cups'] + spec['cups_extended']:
            raise ValueError(f'bra cup {bra.cup!r} is not a {bra.notation.upper()} cup size')
        for category in ACCESSORIES:
            _check(getattr(self.accessories, category), CATALOG['accessories'][category], category)
        return self

    def active(self) -> ClothingSizes:
        return getattr(self, self.system or 'womens')


def legacy(sizes: dict) -> dict:
    """Profiles saved before this chart: {top, bottom, bottom_length, outerwear, shoe, shoe_system}. Values the new
    charts don't list are dropped rather than guessed."""
    system = sizes.get('shoe_system') or 'womens'
    charts = CATALOG[system]
    picks = {}

    def keep(category, value):
        for chart in charts[category]['formats']:
            # Old sizes were US charts or letters (pants never a waist in inches), so other regions' charts don't count.
            us = 'us' in chart.get('regions', ['us'])
            if us and value in chart['options'] and not (category == 'bottoms' and chart['id'] == 'waist'):
                picks[category] = {'format': chart['id'], 'values': [value]}
                return
    for category, key in (('tops', 'top'), ('outerwear', 'outerwear'), ('bottoms', 'bottom'), ('shoes', 'shoe')):
        if sizes.get(key):
            keep(category, str(sizes[key]))
    if sizes.get('bottom_length') in ('short', 'regular', 'long'):
        fit = {'short': 'Petite', 'regular': 'Regular', 'long': 'Tall'}[sizes['bottom_length']]
        picks['dresses'] = {'extras': {'fit': fit}}
    return {'system': system, system: picks}


# Search categories (taste.chat.CATEGORY_WORDS) -> size categories. Skirts shop with dresses.
SEARCH_CATEGORIES = {'top': 'tops', 'bottom': 'bottoms', 'dress': 'dresses', 'outerwear': 'outerwear',
                     'shoes': 'shoes', 'bra': 'bra'}
ACCESSORY_WORDS = (('belts', r'belts?'), ('hats', r'hats?|caps?|beanies?|berets?|fedoras?|bucket hat'),
                   ('gloves', r'gloves?|mittens?'), ('rings', r'rings?'))
# Formats whose values marketplaces print as-is ("M", "8", "W30", "US 8"), so listings can be filtered on them.
FILTERABLE = {'alpha', 'us', 'waist'}
# Country charts: filtered with the country named ("UK 10"), so a US 10 or an EU 10 never passes for it.
REGIONAL = {'uk': 'UK', 'eu': 'EU', 'jp': 'JP'}
SHORT_INSEAM, LONG_INSEAM = 29, 32.5


def accessory_kind(text):
    for kind, pattern in ACCESSORY_WORDS:
        if re.search(rf'\b({pattern})\b', text or '', re.I):
            return kind
    return None


def describe(pick: Pick, spec: dict) -> str:
    chart = next((f for f in spec['formats'] if f['id'] == pick.format), None)
    if not chart or not pick.values:
        return ''
    text = ' or '.join(pick.values) + f' ({chart["label"]})'
    extras = []
    for e in spec.get('extras', []):
        if e['id'] in pick.extras:
            name, unit = re.match(r'(.*?)\s*(?:\((\w+)\))?$', e['label']).groups()
            extras.append(f', {name.lower()} {pick.extras[e["id"]]}{" " + unit if unit else ""}')
    return text + ''.join(extras)


def joined(values, limit=30):
    """Sizes as one filter string ("6/8"), as many as fit the search's 30-character size field."""
    out = ''
    for value in values:
        longer = f'{out}/{value}' if out else value
        if len(longer) > limit:
            break
        out = longer
    return out or None


def for_search(sizing: Sizing, category: str, text: str = '', suggested: ClothingSizes | None = None) -> dict:
    """What a search needs from the shopper's sizes for this kind of item: a size to filter listings on (or None),
    a plain note for Claude, a petite/tall length, and which shoe chart the size uses."""
    system = sizing.system or 'womens'
    sizes = sizing.active()
    out = {'size': None, 'size_note': '', 'length': None, 'shoe_size_system': None}
    if category == 'accessory':
        kind = accessory_kind(text)
        pick = getattr(sizing.accessories, kind) if kind else Pick()
        spec = CATALOG['accessories'][kind] if kind else None
    elif category == 'bra':
        if sizes.bra.size:
            notation = sizes.bra.notation.upper() if sizes.bra.notation != 'asia' else 'Japan'
            out.update(size=sizes.bra.size if sizes.bra.notation == 'us' else None,
                       size_note=f'Bra {sizes.bra.size} ({notation} band and cup)')
        return out
    elif category in SEARCH_CATEGORIES:
        kind = SEARCH_CATEGORIES[category]
        pick, spec = getattr(sizes, kind), CATALOG[system][kind]
        if not pick.values and suggested is not None:
            pick = getattr(suggested, kind)  # filled from body measurements
    else:
        return out
    if not spec or not pick.values:
        return out
    who = {'womens': "women's", 'mens': "men's"}[system]
    out['size_note'] = f'{spec["label"]}: {describe(pick, spec)}' + (f" ({who} chart)" if category != 'accessory' else '')
    if pick.format in FILTERABLE or (category == 'accessory' and pick.format == 'us'):
        out['size'] = joined(pick.values)
    elif pick.format in REGIONAL and category != 'accessory':
        out['size'] = joined(f'{REGIONAL[pick.format]} {v}' for v in pick.values)
    if category == 'shoes':
        out['shoe_size_system'] = system if pick.format == 'us' else None
    fit = pick.extras.get('fit')
    inseam = _number(pick.extras['inseam']) if pick.extras.get('inseam') else (
        _number(pick.extras['inseam_cm']) / 2.54 if pick.extras.get('inseam_cm') else None)
    if fit:
        out['length'] = {'Petite': 'short', 'Regular': 'regular', 'Tall': 'long'}[fit]
    elif inseam:
        out['length'] = 'short' if inseam <= SHORT_INSEAM else 'long' if inseam >= LONG_INSEAM else 'regular'
    return out


def summary(sizing: Sizing) -> str:
    """One line per category the shopper filled in, for the shopping agent."""
    system = sizing.system or 'womens'
    sizes = sizing.active()
    lines = [f'{CATALOG[system][c]["label"]}: {describe(getattr(sizes, c), CATALOG[system][c])}'
             for c in CLOTHING if getattr(sizes, c).values]
    if sizes.bra.size:
        lines.append(f'Bra: {sizes.bra.size} ({sizes.bra.notation.upper()})')
    lines += [f'{CATALOG["accessories"][c]["label"]}: {describe(getattr(sizing.accessories, c), CATALOG["accessories"][c])}'
              for c in ACCESSORIES if getattr(sizing.accessories, c).values]
    return ('Shops in ' + {'womens': "women's", 'mens': "men's"}[system] + ' sizing. ' if sizing.system else '') + '; '.join(lines)
