"""Size matching across marketplaces' free-text size labels ("Small", "S/M", "US S", "XS-S", "One size", "W27").

match() returns True (fits), False (clearly another size) or None (can't tell: no size, or a different sizing
system such as US numeric when the shopper asked for a letter). Callers keep None with a warning.

Numbered sizes belong to a country's chart: "UK 8", "EU 38" and "8 UK" are not a US 8. A size or label without a
country is read as US. Letter sizes are the same everywhere.
"""
import re

LETTERS = ['xxs', 'xs', 's', 'm', 'l', 'xl', 'xxl', 'xxxl']
WORDS = {
    'xx-small': 'xxs', 'xxsmall': 'xxs', 'extra extra small': 'xxs',
    'x-small': 'xs', 'xsmall': 'xs', 'extra small': 'xs',
    'small': 's', 'medium': 'm', 'large': 'l',
    'x-large': 'xl', 'xlarge': 'xl', 'extra large': 'xl', '1x': 'xl',
    'xx-large': 'xxl', 'xxlarge': 'xxl', '2x': 'xxl', '2xl': 'xxl',
    'xxx-large': 'xxxl', '3x': 'xxxl', '3xl': 'xxxl',
}
ONE_SIZE = re.compile(r'\b(one size|os|o/s|free size)\b')
COUNTRIES = {'us': 'us', 'usa': 'us', 'uk': 'uk', 'eu': 'eu', 'eur': 'eu', 'it': 'it', 'fr': 'fr', 'au': 'au',
             'jp': 'jp', 'japan': 'jp'}
_COUNTRY = '|'.join(sorted(COUNTRIES, key=len, reverse=True))
COUNTRY = re.compile(rf'(?<![a-z])({_COUNTRY})\s*(?=\d)|\d(?:\.\d+)?\s*({_COUNTRY})(?![a-z])', re.I)


def tokens(label):
    """Canonical size tokens in a label: letters as 'xs'..'xxxl', numbers as strings ('4', '8.5', '27')."""
    text = str(label).lower().strip()
    for word, letter in sorted(WORDS.items(), key=lambda kv: -len(kv[0])):
        text = re.sub(rf'(?<![a-z]){re.escape(word)}(?![a-z])', f' {letter} ', text)
    found = set()
    for part in re.split(r'[\s/,|()+\-–]+', text):
        part = part.strip('.')
        if part in LETTERS:
            found.add(part)
        elif re.fullmatch(r'[a-z]{0,5}\d+(\.\d+)?([a-z]{2,5})?', part):  # "8", "8.5", "w27", "us4", "10uk"
            found.add(re.sub(r'[a-z]+$', '', re.sub(r'^[a-z]+', '', part)))
    return found


def country(label):
    """The size chart a label names ('uk', 'eu', ...), or None when it names none."""
    found = COUNTRY.search(str(label))
    return COUNTRIES[(found.group(1) or found.group(2)).lower()] if found else None


def charted(labels):
    """(chart, tokens) for each part of each label. "US 6 (UK 10)" is two parts; a part without a country takes the
    one before it in the same label ("EU 38/40")."""
    out = []
    for label in labels:
        current = None
        for part in re.split(r'[/,|()]+', str(label)):
            current = country(part) or current
            if found := tokens(part):
                out.append((current, found))
    return out


def is_letter(size):
    return tokens(size) <= set(LETTERS) and bool(tokens(size))


def match(requested, item_sizes):
    if not requested:
        return True
    want = tokens(requested)
    if not want or not item_sizes:
        return None
    labels = [str(x) for x in item_sizes if x]
    if any(ONE_SIZE.search(x.lower()) for x in labels):
        return True
    chart = country(requested) or 'us'
    have = set()
    for where, found in charted(labels):
        have |= found & set(LETTERS)
        if (where or 'us') == chart:
            have |= found - set(LETTERS)  # numbers only compare within one country's chart
    if not have:
        return None
    if want & have:
        return True
    # Same sizing system but a different size is a clear mismatch; letters vs numbers can't be compared reliably.
    letters_wanted, letters_had = want <= set(LETTERS), have <= set(LETTERS)
    if letters_wanted == letters_had or (letters_wanted and have & set(LETTERS)):
        return False
    return None


def listing_labels(item_sizes, title):
    """Use explicit title sizing when a marketplace omits its structured size field."""
    if any(str(label).strip() for label in item_sizes):
        return item_sizes
    explicit = re.search(r'\bsize\s*[:=-]?\s*(xxxl|xxl|xxs|xl|xs|s|m|l|small|medium|large)\b', title, re.I)
    if explicit:
        return [explicit.group(1)]
    # "UK 10", "EU 38", "size 8", "8 UK", "W28"
    numbered = (re.search(rf'(?<![a-z])(?:{_COUNTRY})\s*\d{{1,2}}(?:\.5)?\b|\b\d{{1,2}}(?:\.5)?\s*(?:{_COUNTRY})\b', title, re.I)
                or re.search(r'\bsize\s*[:=-]?\s*(?:us\s*)?\d{1,2}(?:\.5)?\b', title, re.I)
                or re.search(r'\bW\s?\d{2}\b', title))
    if numbered:
        return [re.sub(r'(?i)^size\s*[:=-]?\s*', '', numbered.group())]
    alpha = re.search(r'\b(?:XXXL|XXL|XXS|XL|XS)\b', title)
    return [alpha.group()] if alpha else []
