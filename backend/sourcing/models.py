from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

Source = Literal['etsy', 'depop', 'poshmark', 'grailed']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class TasteProfile(StrictModel):
    summary: str = Field(max_length=3000)
    colors: list[str] = Field(default_factory=list, max_length=20)
    silhouettes: list[str] = Field(default_factory=list, max_length=20)
    materials: list[str] = Field(default_factory=list, max_length=20)
    avoid: list[str] = Field(default_factory=list, max_length=20)
    reference_image_urls: list[HttpUrl] = Field(default_factory=list, max_length=3)

class ShoppingRequest(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    max_item_price: float = Field(gt=0, le=100000)
    currency: str = Field(default='USD', pattern=r'^[A-Z]{3}$')
    size: str | None = Field(default=None, max_length=30)
    ship_to_country: str = Field(default='US', pattern=r'^[A-Z]{2}$')
    allow_secondhand: bool = True
    unknown_policy: Literal['include_with_warning', 'exclude'] = 'include_with_warning'

class SearchRequest(StrictModel):
    profile_version: str = '1'
    taste_profile: TasteProfile
    request: ShoppingRequest
    sources: list[Source] = Field(default_factory=lambda: ['etsy', 'depop'], min_length=1, max_length=4)
    limit: int = Field(default=12, ge=1, le=24)
    candidates_per_source: int = Field(default=30, ge=1, le=50)
    profile_id: str | None = Field(default=None, max_length=64)  # lets live subscribers find a profile's searches

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
    is_ad: bool | None = None
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
