// Mirrors backend pydantic models (backend/taste/models.py, backend/sourcing/models.py).
// Run the API and open http://127.0.0.1:8000/docs for the authoritative contract.

export type SizeLabel = "XS" | "S" | "M" | "L" | "XL" | "XXL";
// own: the shopper wearing their own clothes, the strongest signal of what they actually wear.
export type Length = "short" | "regular" | "long";
export type ImageKind = "outfit" | "item" | "own";
// mainstream / secondhand are the two Niche Apify actors (backend/actors); the rest are single-marketplace adapters.
export type Source = "mainstream" | "secondhand" | "etsy" | "depop" | "poshmark" | "grailed";
export type Tier =
  | "department" | "mainstream" | "athletic" | "outdoor" | "premium" | "luxury"
  | "fast_fashion" | "off_price" | "big_box" | "marketplace" | "resale" | "small_shop";

export const TIER_LABELS: Record<Tier, string> = {
  department: "Department store", mainstream: "Mainstream", athletic: "Athletic", outdoor: "Outdoor",
  premium: "Premium", luxury: "Luxury", fast_fashion: "Fast fashion", off_price: "Off-price",
  big_box: "Big box", marketplace: "Marketplace", resale: "Secondhand", small_shop: "Small shop",
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

export interface Sizes {
  top: SizeLabel | null;
  /** Pants and skirts: a letter size, or a US numbered size from "00" to "40". */
  bottom: string | null;
  bottom_length?: Length | null;
  outerwear: SizeLabel | null;
  shoe: string | null;
  shoe_system?: "womens" | "mens" | null;
}

export interface Onboarding {
  name: string;
  age: number | null;
  email: string;
  sizes: Sizes;
  measurements?: Measurements;
  budget_min: number;
  budget_max: number;
  currency: string;
  usual_shops: string[];
  favorite_brands?: string[];
}

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
}


export interface ChatTurn {
  role: "user" | "agent";
  text: string;
  brief?: string; // what an agent turn searched for
  proposed?: string; // a search an agent turn offered to run
  proposed_price?: number | null;
  proposed_size?: string | null;
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
