from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sourcing.models import TasteProfile as SourcingProfile

ImageKind = Literal['outfit', 'item', 'own']  # own: the user wearing their own clothes
SizeLabel = Literal['XS', 'S', 'M', 'L', 'XL', 'XXL']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


# Pants and skirts: letters or US numbered sizes, 00 up to 40 (misses through plus).
NUMBERED_SIZES = ['00', '0'] + [str(n) for n in range(2, 41, 2)]
Length = Literal['short', 'regular', 'long']  # petite / regular / tall inseam


class Sizes(StrictModel):
    top: SizeLabel | None = None
    bottom: str | None = None
    bottom_length: Length | None = None
    outerwear: SizeLabel | None = None
    shoe: str | None = Field(default=None, max_length=10)

    @field_validator('bottom')
    @classmethod
    def letter_or_number(cls, size):
        if size is not None and size not in ('XS', 'S', 'M', 'L', 'XL', 'XXL', *NUMBERED_SIZES):
            raise ValueError('bottom size must be XS-XXL or a numbered size from 00 to 40')
        return size


class Onboarding(StrictModel):
    # Mirrors the voice/form setup questions in the design deck.
    name: str = Field(default='', max_length=100)
    age: int | None = Field(default=None, ge=13, le=120)
    email: str = Field(default='', max_length=254)
    sizes: Sizes = Field(default_factory=Sizes)
    budget_min: float = Field(default=0, ge=0)
    budget_max: float = Field(default=150, gt=0, le=100000)
    currency: str = Field(default='USD', pattern=r'^[A-Z]{3}$')
    usual_shops: list[str] = Field(default_factory=list, max_length=20)
    favorite_brands: list[str] = Field(default_factory=list, max_length=30)
    data_consent: bool = False  # agreed that photos and notes go to Claude to build the taste profile


class Garment(StrictModel):
    category: str
    colors: list[str]
    silhouette: str
    pattern: str
    material: str
    details: list[str]
    designer: str | None  # Only when a label/logo is visible; never guessed.


class ImageAnalysis(StrictModel):
    garments: list[Garment]
    aesthetic_tags: list[str]
    liked_aspects: list[str]
    disliked_aspects: list[str]
    confidence_notes: list[str]


class TasteImage(StrictModel):
    id: str
    profile_id: str
    kind: ImageKind
    url: str
    source: Literal['upload', 'pinterest', 'instagram'] = 'upload'
    note: str = ''
    palette: list[str] = []  # Hex colors measured from pixels, not model output.
    analysis: ImageAnalysis | None = None
    created_at: str


class StyleCluster(StrictModel):
    name: str
    description: str
    image_ids: list[str]
    colors: list[str]
    silhouettes: list[str]
    patterns: list[str]


class Profile(StrictModel):
    id: str
    version: int = 0
    onboarding: Onboarding = Field(default_factory=Onboarding)
    summary: str = ''
    clusters: list[StyleCluster] = []
    colors: list[str] = []
    silhouettes: list[str] = []
    patterns: list[str] = []
    materials: list[str] = []
    designers: list[str] = []
    aesthetics: list[str] = []
    avoid: list[str] = []
    # Lookbook notes: what the user described in words when they couldn't find a photo.
    lookbook_notes: list[str] = []
    # The editable "taste prompt": the backend text fed into sourcing and chat agents.
    prompt: str = ''
    mode: Literal['empty', 'fixture', 'claude'] = 'empty'
    updated_at: str = ''

    def to_sourcing(self) -> SourcingProfile:
        ob = self.onboarding
        return SourcingProfile(summary=(self.prompt or self.summary)[:3000], colors=self.colors[:20],
            silhouettes=self.silhouettes[:20], materials=(self.materials + self.patterns)[:20], avoid=self.avoid[:20],
            # Visible designers in liked photos count as brand preferences alongside the ones the user named.
            preferred_brands=list(dict.fromkeys(ob.favorite_brands + self.designers))[:30],
            preferred_stores=ob.usual_shops[:30])


class LookbookNotes(StrictModel):
    notes: list[str] = Field(max_length=20)

    @field_validator('notes')
    @classmethod
    def clean(cls, notes):
        notes = [n.strip()[:500] for n in notes if n.strip()]
        return list(dict.fromkeys(notes))


class ImportRequest(StrictModel):
    url: str = Field(min_length=4, max_length=500)


class NoteUpdate(StrictModel):
    note: str = Field(max_length=1000)


class PromptUpdate(StrictModel):
    prompt: str = Field(min_length=1, max_length=3000)


class EditInstruction(StrictModel):
    instruction: str = Field(min_length=1, max_length=1000)
    source: Literal['text', 'voice'] = 'text'


class ProfileSearch(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    max_item_price: float | None = Field(default=None, gt=0, le=100000)
    size: str | None = Field(default=None, max_length=30)
    length: Length | None = None
    sources: list[Literal['mainstream', 'secondhand', 'etsy', 'depop', 'poshmark', 'grailed']] = ['mainstream', 'secondhand']
    limit: int = Field(default=20, ge=1, le=24)

