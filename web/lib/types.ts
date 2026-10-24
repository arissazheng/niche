// Mirrors backend pydantic models (backend/taste/models.py, backend/sourcing/models.py).
// Run the API and open http://127.0.0.1:8000/docs for the authoritative contract.

export type SizeLabel = "XS" | "S" | "M" | "L" | "XL" | "XXL";
export type ImageKind = "outfit" | "item";
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

export interface Onboarding {
  name: string;
  age: number | null;
  email: string;
  sizes: { top: SizeLabel | null; bottom: SizeLabel | null; outerwear: SizeLabel | null; shoe: string | null };
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
