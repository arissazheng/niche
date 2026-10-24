// Remembers the current profile id in this browser only. Durable user state belongs to the backend / SpacetimeDB.
const KEY = "profile-id";

export function getProfileId(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setProfileId(id: string) {
  try {
    localStorage.setItem(KEY, id);
  } catch {
    // Private mode or blocked storage: the flow still works for this page view.
  }
}

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Niche";
