"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Binder } from "@/components/binder";
import { Drawer } from "@/components/drawer";
import { NoteEditor } from "@/components/note-editor";
import { ProfilePanel } from "@/components/profile-panel";
import { api } from "@/lib/api";
import { getProfileId } from "@/lib/session";
import type { ProfileView, TasteImage } from "@/lib/types";

export default function TastePage() {
  const [view, setView] = useState<ProfileView | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noteFor, setNoteFor] = useState<TasteImage | null>(null);
  const [notesChanged, setNotesChanged] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);

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
    const id = getProfileId();
    if (!id) return setMissing(true);
    run(() => api.getProfile(id));
  }, [run]);

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

  return (
    <div>
      {(notesChanged || rebuilding) && (
        <div className="bg-ink text-paper flex items-center justify-center gap-4 py-2">
          <span className={`label ${rebuilding ? "animate-pulse" : ""}`}>
            {rebuilding ? "Curating your profile…" : "Your notes changed"}
          </span>
          {!rebuilding && (
            <button onClick={rebuild} className="label underline">Rebuild taste profile</button>
          )}
        </div>
      )}
      {view.profile.mode === "fixture" && (
        <p className="label text-center py-1 text-muted">Fixture mode — no Claude call</p>
      )}
      <Binder view={view} onOpenImage={setNoteFor} />
      <div className="px-4 mt-10 mx-auto max-w-3xl grid gap-6">
        <Link href="/upload" className="label underline justify-self-start">← Add or change images</Link>
        <ProfilePanel view={view} onChange={run} />
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
