"""Retailer bank: which stores the mainstream actor keeps, and how each one is labelled.

Google Shopping names a store by its display name ("Zara USA", "Nordstrom Rack"), so each entry lists the
names it may appear under. Adding a store is one line. Tiers are display labels, not ranking boosts.
"""
import re

TIERS = {
    'department': 'Department store',
    'mainstream': 'Mainstream',
    'athletic': 'Athletic',
    'outdoor': 'Outdoor',
    'premium': 'Premium',
    'luxury': 'Luxury',
    'fast_fashion': 'Fast fashion',
    'off_price': 'Off-price',
    'big_box': 'Big box',
    'marketplace': 'Marketplace',
    'resale': 'Secondhand',
    'small_shop': 'Small shop',
    'brand': 'Brand store',
}

# (display name, tier, other names Google Shopping may use)
RETAILERS = [
    # Department stores
    ('Nordstrom', 'department', []),
    ("Dillard's", 'department', ['Dillards']),
    ("Bloomingdale's", 'department', ['Bloomingdales']),
    ("Macy's", 'department', ['Macys']),
    ('Belk', 'department', []),
    ("Kohl's", 'department', ['Kohls']),
    ('JCPenney', 'department', ['JC Penney', 'J.C. Penney']),
    ('Saks Fifth Avenue', 'luxury', ['Saks']),
    ('Neiman Marcus', 'luxury', []),
    ('Von Maur', 'department', []),
    ('Lord & Taylor', 'department', []),
    ('Bergdorf Goodman', 'luxury', []),
    # Mainstream
    ('Gap', 'mainstream', ['Gap Inc', 'Gap Factory']),
    ('Old Navy', 'mainstream', []),
    ('Banana Republic', 'mainstream', ['Banana Republic Factory']),
    ('American Eagle', 'mainstream', ['American Eagle Outfitters', 'AE']),
    ('Aerie', 'mainstream', []),
    ('Hollister', 'mainstream', ['Hollister Co']),
    ('Gilly Hicks', 'mainstream', []),
    ('Abercrombie & Fitch', 'mainstream', ['Abercrombie', 'Abercrombie and Fitch']),
    ("Victoria's Secret", 'mainstream', ['Victorias Secret']),
    ('PINK', 'mainstream', ["Victoria's Secret PINK"]),
    ('White House Black Market', 'mainstream', ['WHBM']),
    ('Uniqlo', 'mainstream', []),
    ('Quince', 'mainstream', []),
    ('J.Crew', 'mainstream', ['J Crew', 'JCrew', 'J.Crew Factory']),
    ('Madewell', 'mainstream', []),
    ('Aritzia', 'premium', []),
    ('Aeropostale', 'mainstream', []),
    ('Ralph Lauren', 'premium', ['Polo Ralph Lauren']),
    ('Urban Outfitters', 'mainstream', []),
    ('Free People', 'mainstream', []),
    ('Anthropologie', 'mainstream', []),
    ('Express', 'mainstream', []),
    ('Guess', 'mainstream', ['GUESS']),
    ("Levi's", 'mainstream', ['Levis', 'Levi Strauss']),
    ('PacSun', 'mainstream', ['Pacific Sunwear']),
    ('Cotton On', 'mainstream', []),
    ('Garage', 'mainstream', ['Garage Clothing']),
    ('Calvin Klein', 'mainstream', []),
    ('Tommy Hilfiger', 'mainstream', []),
    ('L.L.Bean', 'outdoor', ['LL Bean', 'L.L. Bean']),
    ('Talbots', 'mainstream', []),
    ('Reformation', 'premium', []),
    ('Everlane', 'mainstream', []),
    ('Ann Taylor', 'mainstream', []),
    ('LOFT', 'mainstream', ['Ann Taylor LOFT']),
    ('Lands\' End', 'mainstream', ['Lands End']),
    ('Eddie Bauer', 'outdoor', []),
    ('Vince', 'premium', []),
    ('COS', 'premium', []),
    ('Club Monaco', 'premium', []),
    ('Theory', 'premium', []),
    ('Kate Spade', 'premium', ['kate spade new york']),
    ('Tory Burch', 'premium', []),
    ('Coach', 'premium', []),
    ('Michael Kors', 'premium', []),
    ('Skims', 'mainstream', ['SKIMS']),
    ('Savage X Fenty', 'mainstream', []),
    ('UGG', 'mainstream', []),
    ('DSW', 'mainstream', ['Designer Shoe Warehouse']),
    ('Steve Madden', 'mainstream', []),
    ('Sam Edelman', 'mainstream', []),
    ('Dr. Martens', 'mainstream', ['Dr Martens']),
    ('Converse', 'mainstream', []),
    ('Vans', 'mainstream', []),
    ('Revolve', 'premium', []),
    ('Shopbop', 'premium', []),
    ('Garmentory', 'premium', []),
    # Athletic and outdoor
    ('Nike', 'athletic', []),
    ('Adidas', 'athletic', ['adidas']),
    ("Dick's Sporting Goods", 'athletic', ['Dicks Sporting Goods', "DICK'S Sporting Goods"]),
    ('Finish Line', 'athletic', []),
    ('Foot Locker', 'athletic', []),
    ('JD Sports', 'athletic', []),
    ('New Balance', 'athletic', []),
    ('Lululemon', 'athletic', ['lululemon athletica']),
    ('Alo Yoga', 'athletic', ['Alo']),
    ('Vuori', 'athletic', []),
    ('Athleta', 'athletic', []),
    ('Under Armour', 'athletic', []),
    ('Puma', 'athletic', ['PUMA']),
    ("Arc'teryx", 'outdoor', ['Arcteryx']),
    ('Patagonia', 'outdoor', []),
    ('Columbia', 'outdoor', ['Columbia Sportswear']),
    ('The North Face', 'outdoor', ['North Face']),
    ('REI', 'outdoor', ['REI Co-op']),
    # Fast fashion
    ('Zara', 'fast_fashion', ['Zara USA']),
    ('H&M', 'fast_fashion', ['H & M', 'HM']),
    ('Mango', 'fast_fashion', ['MANGO']),
    ('ASOS', 'fast_fashion', []),
    ('Primark', 'fast_fashion', []),
    ('Fashion Nova', 'fast_fashion', []),
    ('Forever 21', 'fast_fashion', []),
    ('Princess Polly', 'fast_fashion', []),
    ('Lulus', 'fast_fashion', ["Lulu's"]),
    ('Edikted', 'fast_fashion', []),
    # Jewelry, bags, hats and sunglasses
    ('Mejuri', 'premium', []),
    ('Kendra Scott', 'mainstream', []),
    ('Pandora', 'mainstream', ['Pandora Jewelry']),
    ('Gorjana', 'premium', []),
    ('BaubleBar', 'mainstream', []),
    ('Ana Luisa', 'premium', []),
    ('Monica Vinader', 'premium', []),
    ('Swarovski', 'premium', []),
    ('Tiffany & Co.', 'luxury', ['Tiffany', 'Tiffany and Co']),
    ('Cuyana', 'premium', []),
    ('Longchamp', 'premium', []),
    ('Rebecca Minkoff', 'premium', []),
    ('Fossil', 'mainstream', []),
    ('Lack of Color', 'premium', []),
    ('Brixton', 'mainstream', []),
    ('Goorin Bros.', 'premium', ['Goorin Bros', 'Goorin']),
    ('Ray-Ban', 'premium', ['Ray Ban']),
    ('Quay Australia', 'mainstream', ['Quay']),
    ('Warby Parker', 'mainstream', []),
    ("Claire's", 'fast_fashion', ['Claires']),
    # Off-price
    ('Nordstrom Rack', 'off_price', []),
    ('Saks Off 5th', 'off_price', ['Saks OFF 5TH']),
    ('Marshalls', 'off_price', []),
    ('T.J. Maxx', 'off_price', ['TJ Maxx', 'TJMaxx']),
    ('Burlington', 'off_price', ['Burlington Coat Factory']),
    ('Ross', 'off_price', ['Ross Dress for Less']),
    ('Neiman Marcus Last Call', 'off_price', ['Last Call']),
    # Big box and marketplaces
    ('Target', 'big_box', []),
    ('Walmart', 'big_box', ['Walmart.com']),
    ('Costco', 'big_box', []),
    ('Amazon', 'marketplace', ['Amazon.com']),
    ('StockX', 'resale', []),
    ('GOAT', 'resale', []),
    ('ThredUp', 'resale', ['thredUP']),
    ('The RealReal', 'resale', []),
    ('Vestiaire Collective', 'resale', []),
    ('Rebag', 'resale', []),
]


def key(name: str) -> str:
    return re.sub(r'[^a-z0-9]', '', name.lower().replace('&', 'and'))


INDEX = {key(alias): (name, tier) for name, tier, aliases in RETAILERS for alias in [name, *aliases]}


def lookup(store_name: str | None):
    """Return (display name, tier) for a store Google Shopping names, or None if it is not in the bank."""
    if not store_name:
        return None
    k = key(store_name)
    if k in INDEX:
        return INDEX[k]
    # "Zara USA", "Gap Factory Store": accept a bank name followed by a regional or channel suffix.
    for suffix in ('usa', 'us', 'store', 'official', 'officialstore', 'online', 'com'):
        if k.endswith(suffix) and k[:-len(suffix)] in INDEX:
            return INDEX[k[:-len(suffix)]]
    return None
