"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

// Saving a result anywhere shows one small note at the bottom of the page, linking to the shortlist; it fades after 5s.
const TOAST_EVENT = "shortlist-toast";
type Toast = { text: string; link: boolean };

export function showToast(text: string, link = true) {
  window.dispatchEvent(new CustomEvent<Toast>(TOAST_EVENT, { detail: { text, link } }));
}

export function ShortlistToast() {
  const [toast, setToast] = useState<(Toast & { at: number }) | null>(null);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const show = (e: Event) => {
      setFading(false);
      setToast({ ...(e as CustomEvent<Toast>).detail, at: Date.now() });
    };
    window.addEventListener(TOAST_EVENT, show);
    return () => window.removeEventListener(TOAST_EVENT, show);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const fade = window.setTimeout(() => setFading(true), 4300);
    const hide = window.setTimeout(() => setToast(null), 5000);
    return () => {
      window.clearTimeout(fade);
      window.clearTimeout(hide);
    };
  }, [toast]);

  if (!toast) return null;
  const body = toast.link ? (
    <Link href="/shortlist" onClick={() => setToast(null)} className="block px-4 py-2 hover:underline">
      {toast.text}
    </Link>
  ) : (
    <span className="block px-4 py-2">{toast.text}</span>
  );
  return (
    <div
      role="status"
      aria-live="polite"
      className={`fixed left-1/2 -translate-x-1/2 bottom-24 z-[1100] bg-ink text-paper text-sm shadow-lg transition-opacity duration-700 ${
        fading ? "opacity-0" : "opacity-100"
      }`}
    >
      {body}
    </div>
  );
}

/**
 * The two things to do with a result you like: Shortlist it (to buy later; checkout starts on the Shortlist page), or
 * add it to your taste profile when it isn't one to buy but really is your style. Both teach the taste profile.
 */
export function ResultActions({
  profileId,
  searchId,
  listingId,
  saved,
  liked,
  onSaved,
  onLiked,
  compact = false,
}: {
  profileId: string;
  searchId: string;
  listingId: string;
  saved: boolean;
  liked: boolean;
  onSaved: () => void;
  onLiked: () => void;
  compact?: boolean;
}) {
  const [busy, setBusy] = useState<"save" | "like" | null>(null);

  async function save() {
    if (saved) return showToast("Already on your shortlist, click here to view");
    setBusy("save");
    try {
      await api.saveToShortlist(profileId, searchId, listingId);
      onSaved();
      showToast("Saved to your shortlist, click here to view");
    } catch (err) {
      showToast((err as Error).message, false);
    } finally {
      setBusy(null);
    }
  }

  async function like() {
    if (liked) return;
    setBusy("like");
    try {
      await api.addToTaste(profileId, searchId, listingId);
      onLiked();
      showToast("Added to your taste profile. We'll look for more like it.", false);
    } catch (err) {
      showToast((err as Error).message, false);
    } finally {
      setBusy(null);
    }
  }

  const size = compact ? "px-2 py-1.5 text-xs" : "px-4 py-2";
  return (
    <div className="flex gap-1.5">
      <button
        type="button"
        onClick={save}
        disabled={busy === "save"}
        aria-pressed={saved}
        className={`label flex-1 border border-ink ${size} ${saved ? "bg-paper" : "bg-ink text-paper hover:opacity-85"} disabled:opacity-60`}
      >
        {busy === "save" ? "Saving…" : saved ? "✓ Shortlisted" : "+ Shortlist"}
      </button>
      <span className="relative group">
        <button
          type="button"
          onClick={like}
          disabled={busy === "like" || liked}
          aria-label="Add to your taste profile so we know you like this"
          aria-pressed={liked}
          aria-busy={busy === "like"}
          className={`label h-full border border-ink ${size} ${liked ? "bg-plinth" : "hover:bg-plinth"}`}
        >
          <span className="inline-flex items-center gap-1">
            <svg aria-hidden="true" viewBox="0 0 24 24" className="size-3.5 shrink-0" fill={liked || busy === "like" ? "#000" : "none"} stroke="#000" strokeWidth="1.6">
              <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" />
            </svg>
            {busy === "like" ? "Adding…" : liked ? "In your taste" : compact ? "Taste" : "Add to taste"}
          </span>
        </button>
        <span
          role="tooltip"
          className="pointer-events-none absolute bottom-full right-0 mb-1 w-48 bg-ink text-paper text-xs px-2 py-1.5 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity z-20"
        >
          {liked
            ? "This is in your taste profile now."
            : "Not buying it? Add it to your taste profile so we know you like this."}
        </span>
      </span>
    </div>
  );
}
