// Remembers the current profile id in this browser only. Durable user state belongs to the backend / SpacetimeDB.
// A tab that chose "Build my own" from a friend's link is a guest: its profile lives in that tab (sessionStorage),
// so a friend trying Niche on the owner's device gets a fresh profile and the owner's own stays untouched.
const KEY = "profile-id";
const GUEST = "guest";

function isGuest() {
  try {
    return sessionStorage.getItem(GUEST) === "1";
  } catch {
    return false;
  }
}

export function getProfileId(): string | null {
  try {
    return isGuest() ? sessionStorage.getItem(KEY) : localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setProfileId(id: string) {
  try {
    (isGuest() ? sessionStorage : localStorage).setItem(KEY, id);
  } catch {
    // Private mode or blocked storage: the flow still works for this page view.
  }
}

/** "Build my own" from a friend's link: this tab starts a new profile of its own. */
export function startGuest() {
  try {
    sessionStorage.setItem(GUEST, "1");
    sessionStorage.removeItem(KEY);
  } catch {
    // storage blocked: the form starts from whatever this browser has
  }
}

/** After "Delete my data": forget the profile and its saved chat in this browser too. */
export function clearProfile(id: string) {
  try {
    (isGuest() ? sessionStorage : localStorage).removeItem(KEY);
    localStorage.removeItem(`shop-chat:${id}`);
  } catch {
    // Nothing stored to clear.
  }
}

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "Niche";

// Friend view: set when this tab opens someone's share link, so the menu shops for them and doesn't open
// Profile / Lookbook (which belong to whoever owns this browser). Per tab; ends when the visitor builds their own.
const FRIEND_KEY = "friend-view";

export interface FriendView {
  token: string;
  name: string;
}

export function getFriendView(): FriendView | null {
  try {
    return JSON.parse(sessionStorage.getItem(FRIEND_KEY) ?? "null") as FriendView | null;
  } catch {
    return null;
  }
}

export function setFriendView(view: FriendView) {
  try {
    sessionStorage.setItem(FRIEND_KEY, JSON.stringify(view));
    window.dispatchEvent(new Event(FRIEND_KEY));
  } catch {
    // storage blocked: the menu just stays as normal
  }
}

export function clearFriendView() {
  try {
    sessionStorage.removeItem(FRIEND_KEY);
    window.dispatchEvent(new Event(FRIEND_KEY));
  } catch {
    // nothing stored
  }
}

export const FRIEND_EVENT = FRIEND_KEY;
