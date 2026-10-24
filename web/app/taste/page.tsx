"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useTable } from "spacetimedb/react";
import { Binder } from "@/components/binder";
import { BuildProgress } from "@/components/build-progress";
import { Drawer } from "@/components/drawer";
import { NoteEditor } from "@/components/note-editor";
import { ProfilePanel } from "@/components/profile-panel";
import { api } from "@/lib/api";
import { getProfileId } from "@/lib/session";
import { tables } from "@/lib/spacetime";
import type { ProfileView, TasteImage } from "@/lib/types";

export default function TastePage() {
  const [profileId, setProfileId] = useState<string | null>(null);
  const [isOwner, setIsOwner] = useState(true);
  const [view, setView] = useState<ProfileView | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noteFor, setNoteFor] = useState<TasteImage | null>(null);
  const [notesChanged, setNotesChanged] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [shared, setShared] = useState(false);

  // Resolves to an error message, or null on success, so the profile panel can show inline feedback.
  const run = useCallback(async (task: () => Promise<ProfileView>) => {
    setError(null);
    try {
      setView(await task());
      return null;
    } catch (err) {
      setError((err as Error).message);
      return (err as Error).message;
    }
  }, []);

  useEffect(() => {
    // `?board=<profile id>` is a shared link: a friend can rearrange the board with you, but not edit the profile.
    const own = getProfileId();
    const board = new URLSearchParams(window.location.search).get("board");
    const id = board ?? own;
    if (!id) return setMissing(true);
    setIsOwner(!board || board === own);
    setProfileId(id);
    run(() => api.getProfile(id));
  }, [run]);

  // Any change to the profile elsewhere (another tab, a voice edit, a rebuild) bumps its live version.
  const [versions] = useTable(tables.profileVersion.where((r) => r.profileId.eq(profileId ?? "")), {
    enabled: !!profileId,
  });
  const liveVersion = versions[0]?.version ?? 0;
  useEffect(() => {
    if (profileId && view && liveVersion > view.profile.version) run(() => api.getProfile(profileId));
  }, [liveVersion, profileId, view, run]);

  if (missing) {
    return (
      <p className="px-4 mt-10 text-display">
        Start with your <Link href="/onboard" className="underline">profile</Link>.
      </p>
    );
  }
  if (!view) return <p className="px-4 mt-10 label">{error ?? "Loading…"}</p>;

  if (view.profile.version === 0) {
    return (
      <p className="px-4 mt-10 text-display">
        <Link href="/upload" className="underline">Upload a few images</Link> and build your profile first.
      </p>
    );
  }

  const id = view.profile.id;
  const ownerName = view.profile.onboarding.name.trim();

  async function saveNote(image: TasteImage, note: string) {
    const failed = await run(async () => {
      await api.setNote(image.id, note);
      return api.getProfile(id);
    });
    if (!failed) {
      setNoteFor(null);
      if (note !== image.note) setNotesChanged(true);
    }
  }

  async function rebuild() {
    setRebuilding(true);
    if (!(await run(() => api.build(id)))) setNotesChanged(false);
    setRebuilding(false);
  }

  async function share() {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/taste?board=${id}`);
      setShared(true);
      window.setTimeout(() => setShared(false), 2500);
    } catch {
      setError("Couldn't copy the link");
    }
  }

  return (
    <div>
      {(notesChanged || rebuilding) && (
        <div className="bg-ink text-paper flex items-center justify-center gap-4 py-2">
          <span className={`label ${rebuilding ? "animate-pulse" : ""}`}>
            {rebuilding ? <BuildProgress profileId={id} /> : "Your notes changed"}
          </span>
          {!rebuilding && (
            <button onClick={rebuild} className="label underline">Rebuild taste profile</button>
          )}
        </div>
      )}
      <div className="flex items-center justify-center gap-4 py-1">
        {view.profile.mode === "fixture" && <span className="label text-muted">Fixture mode — no Claude call</span>}
        {isOwner ? (
          <button onClick={share} className="label underline">
            {shared ? "Link copied — send it to a friend" : "Share board"}
          </button>
        ) : (
          <span className="label">You&apos;re viewing {ownerName ? `${ownerName}'s` : "a shared"} moodboard</span>
        )}
      </div>
      <Binder
        view={view}
        viewerName={isOwner ? ownerName || "Owner" : "Guest"}
        onOpenImage={isOwner ? setNoteFor : undefined}
      />
      <div className="px-4 mt-10 mx-auto max-w-3xl grid gap-6">
        {isOwner ? (
          <>
            <Link href="/upload" className="label underline justify-self-start">← Add or change images</Link>
            <ProfilePanel view={view} onChange={run} />
          </>
        ) : (
          <p className="text-sm">{view.profile.summary}</p>
        )}
      </div>

      <Drawer open={!!noteFor} onClose={() => setNoteFor(null)}>
        {noteFor && (
          <NoteEditor
            key={noteFor.id}
            image={noteFor}
            onSave={(note) => saveNote(noteFor, note)}
            hint="Notes shape your taste profile the next time you rebuild it."
          />
        )}
      </Drawer>
    </div>
  );
}
