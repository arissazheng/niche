"use client";

import { useState } from "react";
import { shareImage } from "@/lib/api";

// Laptop sharing: websites can't post to Instagram or TikTok, so each button downloads the moodboard picture and
// opens the platform in a new tab to upload it. X opens a pre-written post to attach the picture to.

type Platform = "instagram" | "tiktok" | "x";

const TARGETS: Record<Platform, { name: string; format: "story" | "square"; url: string }> = {
  instagram: { name: "Instagram", format: "story", url: "https://www.instagram.com/" },
  tiktok: { name: "TikTok", format: "story", url: "https://www.tiktok.com/upload" },
  x: {
    name: "X",
    format: "square",
    url: `https://x.com/intent/post?text=${encodeURIComponent("My taste, built by Niche from my own photos")}`,
  },
};

export function ShareSocials({ profileId }: { profileId: string }) {
  const [notice, setNotice] = useState<string | null>(null);

  async function share(platform: Platform) {
    const target = TARGETS[platform];
    // Open the tab inside the click so the browser doesn't block it, then download while it loads.
    window.open(target.url, "_blank", "noopener");
    setNotice("Making your moodboard image…");
    try {
      const blob = await shareImage(profileId, target.format);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `niche-moodboard-${target.format}.png`;
      link.click();
      URL.revokeObjectURL(link.href);
      setNotice(
        platform === "x"
          ? "Your moodboard image is downloaded. Attach it to your post on X."
          : `Your moodboard image is downloaded. Upload it on ${target.name}.`,
      );
    } catch (err) {
      setNotice((err as Error).message);
    }
    window.setTimeout(() => setNotice(null), 6000);
  }

  return (
    <div className="flex flex-wrap items-center justify-center gap-3">
      <span className="label">Share</span>
      {(Object.keys(TARGETS) as Platform[]).map((platform) => (
        <button
          key={platform}
          onClick={() => share(platform)}
          aria-label={`Share on ${TARGETS[platform].name}`}
          title={`Share on ${TARGETS[platform].name}`}
          className="size-7 grid place-items-center border border-ink hover:bg-ink hover:text-paper transition-colors"
        >
          <Logo platform={platform} />
        </button>
      ))}
      <span className="label text-muted">The image includes your lookbook photos</span>
      {notice && (
        <p role="status" className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-ink text-paper label px-4 py-3">
          {notice}
        </p>
      )}
    </div>
  );
}

/** Simple monochrome marks, drawn here rather than fetched. */
function Logo({ platform }: { platform: Platform }) {
  const common = { viewBox: "0 0 24 24", className: "size-4", "aria-hidden": true } as const;
  if (platform === "instagram") {
    return (
      <svg {...common} fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="18" height="18" rx="5" />
        <circle cx="12" cy="12" r="4" />
        <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
      </svg>
    );
  }
  if (platform === "tiktok") {
    return (
      <svg {...common} fill="currentColor">
        <path d="M14 3h3c.3 2.2 1.7 3.6 4 3.8v3c-1.5 0-2.8-.4-4-1.2v6.2A5.8 5.8 0 1 1 11.2 9v3.1a2.8 2.8 0 1 0 2.8 2.8V3z" />
      </svg>
    );
  }
  return (
    <svg {...common} fill="currentColor">
      <path d="M17.8 3h3.1l-6.8 7.8L22 21h-6.2l-4.9-6.4L5.3 21H2.2l7.3-8.3L2 3h6.4l4.4 5.8L17.8 3zm-1.1 16.2h1.7L7.4 4.7H5.6l11.1 14.5z" />
    </svg>
  );
}
