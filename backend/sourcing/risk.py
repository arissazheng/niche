"""Buyer-protection warnings for a page of results, shown when a listing is opened (before clicking through to buy).

Rules only, no model calls: each flag points at something the shopper can check themselves on the listing.
"""
import re
from statistics import median

# Sellers steering payment off the marketplace: the buyer loses the platform's (and their card's) protection.
OFF_PLATFORM = re.compile(
    r'\b(venmo|zelle|cash ?app|wire transfer|western union|crypto|bitcoin|whats ?app|telegram'
    r'|paypal (friends|f&f|ff|family)|pay (me )?(directly|outside|off[- ]app)|off[- ](app|platform|site)'
    r'|(dm|text|message|email) (me )?(to|for) (buy|purchase|order|price|payment))\b', re.I)
LOW_RATING = 4.0  # out of 5
TOO_CHEAP = 0.35  # of the median price for the same search
MIN_MEDIAN = 20  # below this, cheap is just cheap


def flag(items):
    """Sets item.risks on each listing, judging price against the other listings in the same search."""
    prices = [x.price for x in items if x.price > 0]
    typical = median(prices) if len(prices) >= 5 else None
    for item in items:
        risks = []
        if typical and typical >= MIN_MEDIAN and 0 < item.price < typical * TOO_CHEAP:
            risks.append(f'Priced far below similar listings (most are around ${typical:.0f}). '
                         'Check the photos, brand and condition before paying.')
        if OFF_PLATFORM.search(f'{item.title}\n{item.description}'):
            risks.append('The listing mentions paying outside the marketplace. Only pay through the site: '
                         'off-platform payments lose buyer and card protection.')
        if item.seller_reviews == 0:
            risks.append('This seller has no reviews yet.')
        elif item.seller_rating is not None and item.seller_rating < LOW_RATING and (item.seller_reviews or 0) >= 3:
            risks.append(f'Seller rated {item.seller_rating:.1f}/5 from {item.seller_reviews} reviews.')
        item.risks = risks
    return items
