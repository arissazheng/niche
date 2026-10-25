"use client";

import { useEffect, useRef, useState } from "react";
import { SectionTitle } from "@/components/chrome";
import { api } from "@/lib/api";
import { SHOPPING, isNo, isYes, useAssistant, useAssistantSkill } from "@/lib/assistant";
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

  // Talking about the taste profile edits it; shopping requests go on to the shopping agent. "No" means different
  // things after "Did I get you right?" (it's off) and after "Anything else?" (all done), so remember which was asked.
  const assistant = useAssistant();
  const asked = useRef<"confirm" | "more">("confirm");
  useAssistantSkill(
    profile.version === 0
      ? null
      : {
          id: "profile",
          label: "Going over your taste profile",
          intro: readBack(profile),
          placeholder: "Less minimal, more vintage",
          async handle(text) {
            if (SHOPPING.test(text)) return null;
            const happy = /^\s*(spot on|perfect|exactly|that'?s (right|me)|you got it|love it)\b/i.test(text);
            if (happy || isYes(text) || (isNo(text) && asked.current === "more")) {
              asked.current = "more";
              return assistant.phrase(
                "They're happy with their taste profile as it is. Suggest going shopping and ask what they're looking for.",
                ["Yay! Then let's go shopping. What are you in the mood for?", "Perfect. Want to go find something? Tell me what you're after.",
                 "Love that. So, what are we shopping for?"],
              );
            }
            if (isNo(text)) {
              return assistant.phrase(
                "They said the read-back of their taste doesn't feel right. Ask what feels off, warmly.",
                ["Oh no, what feels off? Tell me and I'll fix it.", "Okay, what did I miss? Colors, shapes, the overall vibe?"],
              );
            }
            setWorking("Updating your profile…");
            setStatus(null);
            const error = await onChange(() => api.edit(profile.id, text, assistant.mode === "voice" ? "voice" : "text"));
            setWorking(null);
            setStatus(error ? `Couldn't update: ${error}` : `Updated: “${text}”`);
            if (error) return `Hmm, I couldn't update that: ${error}`;
            setFlash(true);
            asked.current = "more";
            return assistant.phrase(
              `Updated their taste profile from what they said: "${text}". Briefly say what changed in plain words, then ask if anything else feels off.`,
              ["Done, that's in your profile now. Anything else feel off?", "Updated! Does the rest feel like you?",
               "Got it, I changed that. Anything else you'd tweak?"],
            );
          },
        },
  );

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

          {!!profile.learned_notes?.length && (
            // Learned from results they shortlisted or added to their taste: how each differed from the rest.
            <div className="grid gap-1">
              <span className="label">Learned from pieces you picked</span>
              <ul className="grid gap-1 text-sm">
                {[...profile.learned_notes].reverse().map((note) => (
                  <li key={note} className="flex items-start justify-between gap-2">
                    <span>{note}</span>
                    <button
                      onClick={() =>
                        update(
                          () => api.setLearned(profile.id, (profile.learned_notes ?? []).filter((x) => x !== note)),
                          "Removing…",
                          "Removed that from your taste profile.",
                        )
                      }
                      disabled={!!working}
                      aria-label="Remove this from your taste profile"
                      className="label text-muted hover:text-ink shrink-0"
                    >
                      ×
                    </button>
                  </li>
                ))}
              </ul>
              <p className="text-xs text-muted">Every search reads these. Tap × if one got you wrong.</p>
            </div>
          )}

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
            <h2 className="text-display">Adjust it</h2>
            <input
              className="input"
              placeholder="Less minimal, more vintage"
              value={instruction}
              disabled={!!working}
              onChange={(e) => setInstruction(e.target.value)}
            />
            <div className="flex justify-between">
              <button type="button" onClick={() => assistant.start("voice")} className="label underline">
                Talk it over
              </button>
              <button disabled={!!working} className="label underline disabled:no-underline disabled:text-muted">
                Apply
              </button>
            </div>
            <p className={`text-xs min-h-4 ${working ? "animate-pulse" : ""}`} role="status" aria-live="polite">
              {working ?? status}
            </p>
          </form>
        </>
      )}
    </aside>
  );
}

/** "Okay, here's what I got from you…": the assistant reads the moodboard back like a friend would. */
function readBack(profile: ProfileView["profile"]) {
  const list = (items: string[]) =>
    items.length > 1 ? `${items.slice(0, -1).join(", ")} and ${items.at(-1)}` : (items[0] ?? "");
  const vibe = list(profile.aesthetics.slice(0, 2).map((x) => x.toLowerCase()));
  const colors = list(profile.colors.filter((x) => !x.startsWith("#")).slice(0, 3).map((x) => x.toLowerCase()));
  const parts = [
    "Okay, so here's what I got from you.",
    vibe && `You're into ${vibe}`,
    colors && `${vibe ? "with" : "You love"} lots of ${colors}`,
  ].filter(Boolean);
  if (parts.length === 1 && profile.summary) parts.push(profile.summary.split(/(?<=\.)\s/)[0]);
  const said = parts.join(" ");
  return `${said}${said.endsWith(".") ? "" : "."} Did I get you right? Tell me anything that feels off.`;
}
