// Mirrors backend pydantic models (backend/taste/models.py, backend/sourcing/models.py).
// Run the API and open http://127.0.0.1:8000/docs for the authoritative contract.

export type SizeLabel = "XS" | "S" | "M" | "L" | "XL" | "XXL";
// own: the shopper wearing their own clothes, the strongest signal of what they actually wear.
export type Length = "short" | "regular" | "long";
export type ImageKind = "outfit" | "item" | "own";
// mainstream / secondhand are the two Niche Apify actors (backend/actors); the rest are single-marketplace adapters.
export type Source = "mainstream" | "secondhand" | "indie" | "etsy" | "depop" | "poshmark" | "grailed";
export type Tier =
  | "department" | "mainstream" | "athletic" | "outdoor" | "premium" | "luxury"
  | "fast_fashion" | "off_price" | "big_box" | "marketplace" | "resale" | "small_shop" | "brand";

export const TIER_LABELS: Record<Tier, string> = {
  department: "Department store", mainstream: "Mainstream", athletic: "Athletic", outdoor: "Outdoor",
  premium: "Premium", luxury: "Luxury", fast_fashion: "Fast fashion", off_price: "Off-price",
  big_box: "Big box", marketplace: "Marketplace", resale: "Secondhand", small_shop: "Small shop", brand: "Brand store",
};

/** Optional body measurements, any or none (backend/taste/models.py Measurements). */
export interface Measurements {
  unit: "in" | "cm";
  shoulder?: number | null;
  bust?: number | null;
  waist?: number | null;
  hips?: number | null;
  inseam?: number | null;
  arm?: number | null;
}

export type SizeSystem = "womens" | "mens";
export type SizeRegion = "us" | "uk" | "eu" | "asia";
/** Sizes in one category: the chart, acceptable sizes in it (several allowed), and extras like inseam or width. */
export interface SizePick {
  format?: string | null;
  values: string[];
  extras: Record<string, string>;
}
export interface ClothingSizes {
  tops: SizePick;
  bottoms: SizePick;
  dresses: SizePick;
  outerwear: SizePick;
  shoes: SizePick;
  bra: { notation?: SizeRegion; band?: string | null; cup?: string | null; size?: string | null };
}
export type ClothingCategory = Exclude<keyof ClothingSizes, "bra">;
export type AccessoryCategory = "belts" | "hats" | "gloves" | "rings";
/** backend/taste/sizing.py. Women's and men's are kept side by side; the system only picks which charts show. */
export interface Sizing {
  system: SizeSystem | null;
  /** Which country charts show first; US by default. */
  region: SizeRegion;
  womens: ClothingSizes;
  mens: ClothingSizes;
  accessories: Record<AccessoryCategory, SizePick>;
}
export interface SizeFormat {
  id: string;
  label: string;
  options: string[];
  custom?: [number, number];
  /** Only shown in these size regions (none = every region). */
  regions?: SizeRegion[];
}
export interface SizeExtra extends SizeFormat {
  formats?: string[];
  /** Hidden behind a small "+ …" link until opened (or filled). */
  tucked?: string;
}
export interface SizeCategorySpec {
  label: string;
  hint?: string;
  optional?: boolean;
  /** Every chart stays available (shoes); the region only picks which opens first. */
  every_region?: boolean;
  formats: SizeFormat[];
  extras?: SizeExtra[];
}
export interface BraChart {
  bands: string[];
  band_custom: [number, number];
  cups: string[];
  cups_extended: string[];
}
export interface SizeCatalog {
  womens: Record<ClothingCategory, SizeCategorySpec>;
  mens: Record<ClothingCategory, SizeCategorySpec>;
  regions: { id: SizeRegion; label: string }[];
  bra: { label: string; regions: Record<SizeRegion, BraChart> };
  accessories: Record<AccessoryCategory, SizeCategorySpec>;
}


export interface Onboarding {
  name: string;
  age: number | null;
  email: string;
  sizing: Sizing;
  measurements?: Measurements;
  budget_min: number;
  budget_max: number;
  currency: string;
  usual_shops: string[];
  favorite_brands?: string[];
  /** Agreed that photos and notes are sent to Claude to build the taste profile. */
  data_consent?: boolean;
  /** "Shops near you": opt-in; only the ZIP code is kept and sent to Gemini (Google Maps). */
  nearby_shops?: boolean;
  zip_code?: string;
}

/** Fields the voice parser heard in a spoken onboarding answer; anything not mentioned is absent. */
export type HeardOnboarding = Partial<
  Pick<Onboarding, "name" | "age" | "email" | "budget_min" | "budget_max" | "currency" | "usual_shops" | "favorite_brands">
> & { measurements?: Partial<Measurements> };

export interface Garment {
  category: string;
  colors: string[];
  silhouette: string;
  pattern: string;
  material: string;
  details: string[];
  designer: string | null;
}

export interface TasteImage {
  id: string;
  profile_id: string;
  kind: ImageKind;
  url: string;
  source?: "upload" | "pinterest" | "instagram" | "tiktok";
  note: string;
  palette: string[];
  analysis: {
    garments: Garment[];
    aesthetic_tags: string[];
    liked_aspects: string[];
    disliked_aspects: string[];
    confidence_notes: string[];
  } | null;
  created_at: string;
}

export interface StyleCluster {
  name: string;
  description: string;
  image_ids: string[];
  colors: string[];
  silhouettes: string[];
  patterns: string[];
}

export interface Profile {
  id: string;
  version: number;
  onboarding: Onboarding;
  summary: string;
  clusters: StyleCluster[];
  colors: string[];
  silhouettes: string[];
  patterns: string[];
  materials: string[];
  designers: string[];
  aesthetics: string[];
  avoid: string[];
  lookbook_notes?: string[];
  prompt: string;
  mode: "empty" | "fixture" | "claude";
  updated_at: string;
}

export interface ProfileView {
  profile: Profile;
  images: TasteImage[];
  /** Built, and nothing in the lookbook or preferences has changed since, so there's nothing to rebuild. */
  up_to_date?: boolean;
}

export interface Listing {
  id: string;
  source: Source;
  title: string;
  url: string;
  image_urls: string[];
  price: number;
  currency: string;
  seller: string | null;
  retailer: string | null;
  tier: Tier | null;
  brand: string | null;
  condition: string | null;
  sizes: string[];
  warnings: string[];
  /** Scam / buyer-protection warnings (low price for the search, off-platform payment, poorly reviewed seller). */
  risks?: string[];
  seller_rating?: number | null;
  seller_reviews?: number | null;
  score: number | null;
  reason: string;
  is_fixture: boolean;
}

export type SearchStatus = "queued" | "running" | "completed" | "partial" | "failed" | "interrupted";

export interface SearchJob {
  search_id: string;
  status: SearchStatus;
  results?: Listing[];
  warnings?: string[];
  queries?: string[];
  ranking_method?: string;
  counts?: SearchCounts;
}

/** What the search looked through and why listings were left out (set when it finishes). */
export interface SearchCounts {
  retrieved: number;
  eligible: number;
  left_out?: Partial<Record<"wrong_size" | "over_price" | "sold" | "excluded_brand", number>>;
  max_item_price?: number;
}


export interface ChatTurn {
  role: "user" | "agent";
  text: string;
  brief?: string; // what an agent turn searched for
  proposed?: string; // a search an agent turn offered to run
  proposed_price?: number | null;
  proposed_size?: string | null;
  proposed_must_have?: string[] | null; // visible features the offered search needs (asymmetric, button-front…)
  proposed_category?: string | null;
  proposed_brands?: string[] | null;
  linked?: LinkedPage[]; // product links the agent read from the user's message
}

export interface LinkedPage {
  url: string;
  site?: string | null;
  title?: string | null;
  readable: boolean;
}

export interface Budget {
  linked: boolean;
  balance?: number;
  monthly_budget?: number;
  month_spent?: number;
  remaining?: number;
  upcoming_bills?: { payee: string; amount: number; due: string }[];
}

export interface AgentReply {
  reply: string;
  action: "reply" | "propose" | "search";
  brief: string;
  max_item_price?: number | null;
  size?: string | null; // the user's profile size for this garment unless they named one
  must_have?: string[];
  category?: string;
  brands?: string[];
  linked?: LinkedPage[];
  budget?: Omit<Budget, "linked"> | null;
  search_id?: string;
  status_url?: string;
}

/** A Pinterest/Instagram import running in the background (backend/taste/imports.py). */
export interface ImportJob {
  id: string;
  site: "pinterest" | "instagram" | "tiktok";
  kind: "board" | "profile" | "post";
  url: string;
  status: "running" | "done" | "empty" | "failed";
  added: number;
  message: string;
  created_at: string;
}

/** Real shops near the shopper's ZIP worth checking for a search (Gemini with Google Maps grounding). */
export interface NearbyShops {
  enabled: boolean;
  zip_code?: string;
  unavailable?: boolean;
  shops: { name: string; why: string; maps_url: string }[];
}
