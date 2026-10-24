"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { SectionTitle } from "@/components/chrome";
import { VoiceButton } from "@/components/voice";
import { api } from "@/lib/api";
import type { ProfileView } from "@/lib/types";

export type Change = (task: () => Promise<ProfileView>) => Promise<string | null>;

export function ProfilePanel({ view, onChange }: { view: ProfileView; onChange: Change }) {
  const { profile } = view;
  const [prompt, setPrompt] = useState(profile.prompt);
  const [instruction, setInstruction] = useState("");
  const [working, setWorking] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  useEffect(() => setPrompt(profile.prompt), [profile.prompt]);
  useEffect(() => {
    if (!flash) return;
    const timer = window.setTimeout(() => setFlash(false), 2500);
    return () => window.clearTimeout(timer);
  }, [flash]);

  async function update(task: () => Promise<ProfileView>, pending: string, done: string) {
    setWorking(pending);
    setStatus(null);
    const error = await onChange(task);
    setWorking(null);
    setStatus(error ? `Couldn't update: ${error}` : done);
    if (!error) setFlash(true);
  }

  function adjust(text: string, source: "text" | "voice") {
    return update(() => api.edit(profile.id, text, source), "Updating your profile…", `Updated: “${text}”`);
  }

  // Changed sections briefly turn grey so it's obvious where an edit landed.
  const changed = `transition-colors duration-700 ${flash ? "bg-plinth" : ""}`;

  const lists: [string, string[]][] = [
    ["Colors", profile.colors],
    ["Silhouettes", profile.silhouettes],
    ["Patterns", profile.patterns],
    ["Materials", profile.materials],
    ["Designers", profile.designers],
    ["Aesthetics", profile.aesthetics],
    ["Avoid", profile.avoid],
  ];

  return (
    <aside className="grid gap-4 content-start">
      <SectionTitle aside={`v${profile.version}`}>Taste profile</SectionTitle>
      {profile.version === 0 ? (
        <p className="text-sm">Upload a few images and build your profile to see it here.</p>
      ) : (
        <>
          <p className={`text-sm ${changed}`}>{profile.summary}</p>
          <dl className={`grid gap-1 text-sm ${changed}`}>
            {lists.filter(([, v]) => v.length).map(([k, v]) => (
              <div key={k} className="grid grid-cols-[6rem_1fr] gap-2">
                <dt className="label pt-0.5">{k}</dt>
                <dd>{v.join(", ")}</dd>
              </div>
            ))}
          </dl>

          <div className="grid gap-2">
            <span className="label">What the shopping agent reads (editable)</span>
            <textarea
              className={`input min-h-48 text-sm ${changed}`}
              value={prompt}
              disabled={!!working}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <button
              disabled={!!working || prompt === profile.prompt || !prompt.trim()}
              onClick={() => update(() => api.setPrompt(profile.id, prompt), "Saving…", "Saved your text.")}
              className="label self-end underline disabled:no-underline disabled:text-muted"
            >
              Save text
            </button>
          </div>

          <form
            className="grid gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!instruction.trim() || working) return;
              adjust(instruction.trim(), "text");
              setInstruction("");
            }}
          >
            <span className="label">Adjust it</span>
            <input
              className="input"
              placeholder="Less minimal, more vintage"
              value={instruction}
              disabled={!!working}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <div className="flex justify-between">
              <VoiceButton
                context="profile-review"
                label="Review out loud"
                onTranscript={(t) => adjust(t, "voice")}
              />
              <button disabled={!!working} className="label underline disabled:no-underline disabled:text-muted">
                Apply
              </button>
            </div>
            <p className={`text-xs min-h-4 ${working ? "animate-pulse" : ""}`} role="status" aria-live="polite">
              {working ?? status}
            </p>
          </form>

          <Link href="/shop" className="rule-t rule-b text-display py-2 text-center">Shop this taste</Link>
        </>
      )}
    </aside>
  );
}
