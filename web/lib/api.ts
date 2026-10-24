import type { AgentReply, ChatTurn, CheckoutIntent, ImageKind, Onboarding, ProfileView, SearchJob, Source, TasteImage } from "./types";

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

export const api = {
  createProfile: (onboarding: Partial<Onboarding>) =>
    request<ProfileView>("/v1/taste/profiles", { method: "POST", body: json(onboarding) }),
  getProfile: (id: string) => request<ProfileView>(`/v1/taste/profiles/${id}`),
  uploadImage: (id: string, file: File, kind: ImageKind) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return request<TasteImage>(`/v1/taste/profiles/${id}/images`, { method: "POST", body: form });
  },
  setNote: (imageId: string, note: string) =>
    request<TasteImage>(`/v1/taste/images/${imageId}/note`, { method: "PUT", body: json({ note }) }),
  deleteImage: (imageId: string) => request<void>(`/v1/taste/images/${imageId}`, { method: "DELETE" }),
  build: (id: string) => request<ProfileView>(`/v1/taste/profiles/${id}/build`, { method: "POST" }),
  edit: (id: string, instruction: string, source: "text" | "voice" = "text") =>
    request<ProfileView>(`/v1/taste/profiles/${id}/edit`, { method: "POST", body: json({ instruction, source }) }),
  setPrompt: (id: string, prompt: string) =>
    request<ProfileView>(`/v1/taste/profiles/${id}/prompt`, { method: "PUT", body: json({ prompt }) }),
  search: (id: string, query: string, sources?: Source[]) =>
    request<{ search_id: string; status_url: string }>(`/v1/taste/profiles/${id}/searches`, {
      method: "POST",
      body: json({ query, ...(sources && { sources }) }),
    }),
  chat: (id: string, messages: ChatTurn[]) =>
    request<AgentReply>(`/v1/taste/profiles/${id}/chat`, { method: "POST", body: json({ messages }) }),
  getSearch: (statusUrl: string) => request<SearchJob>(statusUrl),
  checkoutIntent: (search_id: string, listing_id: string) =>
    request<CheckoutIntent>("/v1/checkout/intents", { method: "POST", body: json({ search_id, listing_id }) }),
  confirmCheckout: (payment_intent_id: string) =>
    request<{ status: string; ledger: unknown }>("/v1/checkout/confirm", {
      method: "POST",
      body: json({ payment_intent_id }),
    }),
};
