"""Size matching across marketplaces' free-text size labels ("Small", "S/M", "US S", "XS-S", "One size", "W27").

match() returns True (fits), False (clearly another size) or None (can't tell: no size, or a different sizing
system such as US numeric when the shopper asked for a letter). Callers keep None with a warning.
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
        elif re.fullmatch(r'[a-z]{0,2}\d+(\.\d+)?', part):  # "8", "8.5", "w27", "us4"
            found.add(re.sub(r'^[a-z]+', '', part))
    return found


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
    have = set().union(*(tokens(x) for x in labels)) if labels else set()
    if not have:
        return None
    if want & have:
        return True
    # Same sizing system but a different size is a clear mismatch; letters vs numbers can't be compared reliably.
    letters_wanted, letters_had = want <= set(LETTERS), have <= set(LETTERS)
    if letters_wanted == letters_had or (letters_wanted and have & set(LETTERS)):
        return False
    return None
