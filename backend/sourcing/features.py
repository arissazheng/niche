"""A fixed vocabulary of visible garment features. Claude tags pre-loaded listings from their photos, and the chat agent
picks the request's must-haves from the same list, so matching them is a set intersection: instant, no extra call."""

FEATURES = [
    # shape and fit
    'asymmetric', 'cropped', 'oversized', 'fitted', 'boxy', 'longline', 'wide-leg', 'straight-leg', 'flared',
    'bodycon', 'a-line', 'pleated', 'draped', 'ruched', 'peplum',
    # fastening and front
    'button-front', 'zip-front', 'wrap', 'lace-up', 'double-breasted', 'tie-front',
    # neck, shoulders and sleeves
    'high-collar', 'collared', 'turtleneck', 'halter', 'strapless', 'off-shoulder', 'one-shoulder', 'v-neck',
    'square-neck', 'cowl-neck', 'sleeveless', 'puff-sleeve', 'long-sleeve', 'hooded',
    # details and trims
    'fur-trim', 'shearling', 'lace', 'sheer', 'ruffles', 'bow', 'embroidered', 'studs', 'chains', 'cut-out',
    'corset-boning', 'belted', 'fringe', 'quilted', 'patchwork', 'distressed', 'pockets',
    # surface
    'leather', 'faux-leather', 'denim', 'knit', 'satin', 'velvet', 'mesh', 'striped', 'plaid', 'floral', 'animal-print',
    'polka-dot', 'pinstripe', 'metallic',
]
VOCAB = set(FEATURES)


def clean(values):
    """Only vocabulary terms, deduplicated, in order."""
    return list(dict.fromkeys(v for v in values or [] if v in VOCAB))
