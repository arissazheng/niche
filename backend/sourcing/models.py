from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

# mainstream / secondhand / indie are Niche's Apify actors (backend/actors); web is independent shops found through
# Bright Data (sourcing/webshops.py); the others are single-marketplace adapters.
Source = Literal['mainstream', 'secondhand', 'indie', 'web', 'etsy', 'depop', 'poshmark', 'grailed']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class IndieShop(StrictModel):
    """An independent label's own Shopify store, read by niche-indie (backend/actors/niche_actors/indie.py)."""
    domain: str = Field(pattern=r'^[a-z0-9-]+(\.[a-z0-9-]+)+$', max_length=100)
    name: str = Field(min_length=1, max_length=80)
    currency: str = Field(default='USD', pattern=r'^[A-Z]{3}$')
    # shopify: niche-indie reads its catalog. web: any other platform, found and read through Bright Data
    # (sourcing/webshops.py).
    platform: Literal['shopify', 'web'] = 'shopify'
    # Verified independent: passed every check in taste/brands.py (None: couldn't be checked, e.g. not Shopify).
    verified: bool | None = None
    checks: dict[str, bool | None] = {}

class TasteProfile(StrictModel):
    summary: str = Field(max_length=3000)
    colors: list[str] = Field(default_factory=list, max_length=20)
    silhouettes: list[str] = Field(default_factory=list, max_length=20)
    materials: list[str] = Field(default_factory=list, max_length=20)
    avoid: list[str] = Field(default_factory=list, max_length=20)
    # Brands and stores the user asked for; used in queries and as a modest ranking boost, never over taste fit.
    preferred_brands: list[str] = Field(default_factory=list, max_length=30)
    preferred_stores: list[str] = Field(default_factory=list, max_length=30)
    # The shopper's own independent shops, searched alongside niche-indie's seed list.
    indie_shops: list[IndieShop] = Field(default_factory=list, max_length=30)
    reference_image_urls: list[HttpUrl] = Field(default_factory=list, max_length=3)

class ShoppingRequest(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    max_item_price: float = Field(gt=0, le=100000)
    currency: str = Field(default='USD', pattern=r'^[A-Z]{3}$')
    size: str | None = Field(default=None, max_length=30)
    length: Literal['short', 'regular', 'long'] | None = None  # pants/skirts: petite, regular or tall
    shoe_size_system: Literal['womens', 'mens'] | None = None  # which shoe size chart `size` uses
    # The shopper's sizes for this kind of item in words ("Bottoms: 30 or 31 (Waist (in)), inseam 32 (men's chart)").
    size_note: str = Field(default='', max_length=500)
    # The shopper's body measurements in inches (any of shoulder, bust, waist, hips, inseam, arm), for fit checks.
    measurements: dict[str, float] = Field(default_factory=dict)
    # Visible features the request can't do without (sourcing/features.py), e.g. asymmetric + button-front.
    must_have: list[str] = Field(default_factory=list, max_length=8)
    brands: list[str] = Field(default_factory=list, max_length=3)  # brands the shopper named ("like Lewkin")
    # What kind of item this is (top, dress, outerwear...), from the chat agent; decides which pre-loaded listings fit.
    category: str | None = Field(default=None, max_length=20)
    ship_to_country: str = Field(default='US', pattern=r'^[A-Z]{2}$')
    allow_secondhand: bool = True
    unknown_policy: Literal['include_with_warning', 'exclude'] = 'include_with_warning'

class SearchRequest(StrictModel):
    profile_version: str = '1'
    taste_profile: TasteProfile
    request: ShoppingRequest
    sources: list[Source] = Field(default_factory=lambda: ['mainstream', 'secondhand'], min_length=1, max_length=6)
    limit: int = Field(default=20, ge=1, le=24)
    candidates_per_source: int = Field(default=30, ge=1, le=50)
    profile_id: str | None = Field(default=None, max_length=64)  # lets live subscribers find a profile's searches
    # Started by a friend through a share link (gift shopping): ranked with this profile's taste, but kept out of the
    # live per-profile feed and never recorded against the profile's bank.
    for_friend: bool = False

class Listing(StrictModel):
    id: str
    source: Source
    title: str
    url: str
    image_urls: list[str] = []
    description: str = ''
    price: float
    currency: str
    sizes: list[str] = []
    condition: str | None = None
    available: bool | None = None
    seller: str | None = None
    seller_type: str = 'unknown'
    marketplace: str | None = None  # where the row came from, e.g. depop, vinted, google_shopping
    retailer: str | None = None  # display store name, e.g. Nordstrom, Depop
    tier: str | None = None  # retailer type from backend/actors/niche_actors/retailers.py, e.g. department, resale
    brand: str | None = None
    is_ad: bool | None = None
    seller_rating: float | None = None  # 0-5, where the marketplace gives it
    seller_reviews: int | None = None
    features: list[str] = []  # visible features Claude tagged from the photo (pre-loaded listings only)
    copies: int = 1  # how many identical listings (same title and price) were found; only the best one is shown
    risks: list[str] = []  # scam / buyer-protection warnings, shown before the shopper clicks through (sourcing/risk.py)
    shipping_cost: float | None = None
    ships_to: list[str] | None = None
    scraped_at: str
    provenance: dict = {}
    warnings: list[str] = []
    score: float | None = None
    match_dimensions: dict[str, float] = {}
    reason: str = ''
    is_fixture: bool = False

class Feedback(StrictModel):
    listing_id: str
    liked: bool
    comment: str = Field(default='', max_length=1000)
