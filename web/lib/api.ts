import type { AgentReply, BrandSuggestion, Budget, ChatTurn, ClothingSizes, HeardOnboarding, ImageKind, ImportJob, Measurements, NearbyShops, Onboarding, ProfileView, SearchJob, SizeCatalog, ShortlistItem, ShortlistView, SizeSystem, Source, TasteImage, PriceCheck } from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" };
  const response = await fetch(`${API_URL}${path}`, { ...init, headers: { ...headers, ...init?.headers } });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(typeof detail?.detail === "string" ? detail.detail : `Request failed (${response.status})`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

const json = (body: unknown) => JSON.stringify(body);

/** The owner's moodboard as a PNG to post: "story" (9:16) for Instagram / TikTok, "square" for X. */
export async function shareImage(profileId: string, format: "story" | "square"): Promise<Blob> {
  const response = await fetch(`${API_URL}/v1/taste/profiles/${profileId}/share-image?format=${format}`);
  if (!response.ok) throw new Error(`Couldn't make the image (${response.status})`);
  return response.blob();
}

export const api = {
  sizingCatalog: () => request<SizeCatalog>("/v1/taste/sizing/catalog"),
  suggestSizes: (measurements: Measurements, system: SizeSystem) =>
    request<ClothingSizes>(`/v1/taste/sizes/suggest?system=${system}`, { method: "POST", body: json(measurements) }),
  createProfile: (onboarding: Partial<Onboarding>) =>
    request<ProfileView>("/v1/taste/profiles", { method: "POST", body: json(onboarding) }),
  getProfile: (id: string) => request<ProfileView>(`/v1/taste/profiles/${id}`),
  updateOnboarding: (id: string, onboarding: Onboarding) =>
    request<ProfileView>(`/v1/taste/profiles/${id}/onboarding`, { method: "PUT", body: json(onboarding) }),
  uploadImage: (id: string, file: File, kind: ImageKind) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return request<TasteImage>(`/v1/taste/profiles/${id}/images`, { method: "POST", body: form });
  },
  setNote: (imageId: string, note: string) =>
    request<TasteImage>(`/v1/taste/images/${imageId}/note`, { method: "PUT", body: json({ note }) }),
  imageFromUrl: (id: string, url: string, kind: ImageKind = "outfit") =>
    request<TasteImage>(`/v1/taste/profiles/${id}/images/from-url`, { method: "POST", body: json({ url, kind }) }),
  /** The assistant's spoken reaction to photos just added. */
  reactToPhotos: (id: string, imageIds: string[]) =>
    request<{ text: string }>(`/v1/taste/profiles/${id}/react`, { method: "POST", body: json({ image_ids: imageIds }) }),
  setLookbookNotes: (id: string, notes: string[]) =>
    request<ProfileView>(`/v1/taste/profiles/${id}/notes`, { method: "PUT", body: json({ notes }) }),
  importLink: (id: string, url: string) =>
    request<ImportJob>(`/v1/taste/profiles/${id}/imports`, { method: "POST", body: json({ url }) }),
  imports: (id: string) => request<ImportJob[]>(`/v1/taste/profiles/${id}/imports`),
  nearby: (id: string, searchId: string) =>
    request<NearbyShops>(`/v1/taste/profiles/${id}/nearby?search_id=${encodeURIComponent(searchId)}`),
  addShop: (id: string, shop: string) =>
    request<ProfileView>(`/v1/taste/profiles/${id}/shops`, { method: "POST", body: json({ shop }) }),
  brandSuggestions: (id: string) =>
    request<{ suggestions: BrandSuggestion[] }>(`/v1/taste/profiles/${id}/brands/suggestions`),
  removeShop: (id: string, domain: string) =>
    request<ProfileView>(`/v1/taste/profiles/${id}/shops/${encodeURIComponent(domain)}`, { method: "DELETE" }),
  deleteProfile: (id: string) => request<void>(`/v1/taste/profiles/${id}`, { method: "DELETE" }),
  deleteImage: (imageId: string) => request<void>(`/v1/taste/images/${imageId}`, { method: "DELETE" }),
  build: (id: string) => request<ProfileView>(`/v1/taste/profiles/${id}/build`, { method: "POST" }),
  edit: (id: string, instruction: string, source: "text" | "voice" = "text") =>
    request<ProfileView>(`/v1/taste/profiles/${id}/edit`, { method: "POST", body: json({ instruction, source }) }),
  setPrompt: (id: string, prompt: string) =>
    request<ProfileView>(`/v1/taste/profiles/${id}/prompt`, { method: "PUT", body: json({ prompt }) }),
  priceCheck: (searchId: string, listingId: string) =>
    request<PriceCheck>(`/v1/searches/${searchId}/listings/${encodeURIComponent(listingId)}/price-check`),
  search: (
    id: string,
    query: string,
    options: { sources?: Source[]; maxItemPrice?: number | null; size?: string | null; mustHave?: string[] | null; category?: string | null; brands?: string[] | null } = {},
  ) =>
    request<{ search_id: string; status_url: string }>(`/v1/taste/profiles/${id}/searches`, {
      method: "POST",
      body: json({
        query,
        ...(options.sources && { sources: options.sources }),
        ...(options.maxItemPrice && { max_item_price: options.maxItemPrice }),
        ...(options.size && { size: options.size }),
        ...(options.mustHave?.length && { must_have: options.mustHave }),
        ...(options.category && { category: options.category }),
        ...(options.brands?.length && { brands: options.brands }),
      }),
    }),
  share: (id: string) => request<{ token: string }>(`/v1/taste/profiles/${id}/share`, { method: "POST" }),
  unshare: (id: string) => request<void>(`/v1/taste/profiles/${id}/share`, { method: "DELETE" }),
  /** A friend's board through their share link: taste and photos, first name only. */
  shared: (token: string) => request<ProfileView>(`/v1/taste/shared/${encodeURIComponent(token)}`),
  /** Shopping for the friend who shared the link: their taste and sizes, your price. */
  giftChat: (token: string, messages: ChatTurn[], searchId?: string | null) =>
    request<AgentReply>(`/v1/taste/shared/${encodeURIComponent(token)}/chat`, {
      method: "POST",
      body: json({ messages, ...(searchId && { search_id: searchId }) }),
    }),
  chat: (id: string, messages: ChatTurn[], searchId?: string | null, useBudget = false) =>
    request<AgentReply>(`/v1/taste/profiles/${id}/chat`, {
      method: "POST",
      body: json({ messages, ...(searchId && { search_id: searchId }), ...(useBudget && { use_budget: true }) }),
    }),
  budget: (id: string) => request<Budget>(`/v1/taste/profiles/${id}/budget`),
  markBought: (search_id: string, listing_id: string) =>
    request<{ recorded: boolean; reason: string | null; ledger?: { amount: number } | null }>("/v1/checkout/mark-bought", {
      method: "POST",
      body: json({ search_id, listing_id }),
    }),
  shortlist: (id: string) => request<ShortlistView>(`/v1/taste/profiles/${id}/shortlist`),
  /** Saves a result to buy later; the taste profile also learns how it differed from the rest of the search. */
  saveToShortlist: (id: string, search_id: string, listing_id: string, collection?: string | null) =>
    request<{ item: ShortlistItem; added: boolean; learned: string | null }>(`/v1/taste/profiles/${id}/shortlist`, {
      method: "POST",
      body: json({ search_id, listing_id, ...(collection && { collection }) }),
    }),
  moveShortlistItem: (id: string, itemId: string, collection: string | null) =>
    request<ShortlistView>(`/v1/taste/profiles/${id}/shortlist/${itemId}`, { method: "PUT", body: json({ collection }) }),
  removeShortlistItem: (id: string, itemId: string) =>
    request<ShortlistView>(`/v1/taste/profiles/${id}/shortlist/${itemId}`, { method: "DELETE" }),
  addCollection: (id: string, name: string) =>
    request<ShortlistView>(`/v1/taste/profiles/${id}/collections`, { method: "POST", body: json({ name }) }),
  removeCollection: (id: string, name: string) =>
    request<ShortlistView>(`/v1/taste/profiles/${id}/collections/${encodeURIComponent(name)}`, { method: "DELETE" }),
  /** "Not to buy, but this is so me": only the taste profile learns from it. */
  addToTaste: (id: string, search_id: string, listing_id: string) =>
    request<ProfileView & { learned: string }>(`/v1/taste/profiles/${id}/liked`, {
      method: "POST",
      body: json({ search_id, listing_id }),
    }),
  setLearned: (id: string, notes: string[]) =>
    request<ProfileView>(`/v1/taste/profiles/${id}/learned`, { method: "PUT", body: json({ notes }) }),
  getSearch: (statusUrl: string) => request<SearchJob>(statusUrl),
  transcribe: (audio: Blob) => {
    const form = new FormData();
    const ext = audio.type.includes("wav") ? "wav" : audio.type.includes("mp4") ? "mp4" : audio.type.includes("ogg") ? "ogg" : "webm";
    form.append("file", audio, `speech.${ext}`);
    return request<{ text: string }>("/v1/voice/transcribe", { method: "POST", body: form });
  },
  /** The assistant's reply as speech (MP3). */
  speak: async (text: string, voice?: string | null) => {
    const response = await fetch(`${API_URL}/v1/voice/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: json({ text: text.slice(0, 1500), ...(voice && { voice }) }),
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(typeof detail?.detail === "string" ? detail.detail : `Request failed (${response.status})`);
    }
    return response.arrayBuffer();
  },
  /** The assistant's next line in its own words (falls back to `fallback` without Claude). */
  voices: () => request<{ key: string; name: string }[]>("/v1/voice/voices"),
  line: (body: { page: string; heard: string; facts: string; fallback: string; recent: string[]; profile_id?: string | null }) =>
    request<{ text: string }>("/v1/voice/line", { method: "POST", body: json(body) }),
  voiceStatus: () => request<{ enabled: boolean; provider: string }>("/v1/voice/status"),
  /** Onboarding answers spoken out loud → only the form fields the user mentioned. */
  heardOnboarding: (transcript: string, shopOptions: string[]) =>
    request<HeardOnboarding>("/v1/voice/onboarding", {
      method: "POST",
      body: json({ transcript, shop_options: shopOptions }),
    }),
};
