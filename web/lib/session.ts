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

/** After "Delete my data": forget the profile and its saved chat in this browser too. */
export function clearProfile(id: string) {
  try {
    localStorage.removeItem(KEY);
    localStorage.removeItem(`shop-chat:${id}`);
  } catch {
    // Nothing stored to clear.
  }
}

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Niche";
