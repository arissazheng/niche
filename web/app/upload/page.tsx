"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { SectionTitle } from "@/components/chrome";
import { Drawer } from "@/components/drawer";
import { ImageTile } from "@/components/image-tile";
import { NoteEditor } from "@/components/note-editor";
import { api } from "@/lib/api";
import { getProfileId } from "@/lib/session";
import type { ImageKind, ProfileView, TasteImage } from "@/lib/types";

export default function UploadPage() {
  const [view, setView] = useState<ProfileView | null>(null);
  const [missing, setMissing] = useState(false);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noteFor, setNoteFor] = useState<TasteImage | null>(null);
  const router = useRouter();

  // Resolves to an error message, or null on success, so callers can show inline feedback.
  const run = useCallback(async (task: () => Promise<ProfileView | void>) => {
    setError(null);
    try {
      const next = await task();
      if (next) setView(next);
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
  if (!view) return <p className="px-4 mt-10 label">Loading…</p>;

  const { profile, images } = view;
  const id = profile.id;
  const refresh = () => api.getProfile(id);

  async function upload(files: FileList | null, kind: ImageKind) {
    if (!files) return;
    await run(async () => {
      for (const file of Array.from(files)) await api.uploadImage(id, file, kind);
      return refresh();
    });
  }

  async function build() {
    setBuilding(true);
    const error = await run(() => api.build(id));
    if (!error) return router.push("/taste");
    setBuilding(false);
  }

  if (building) {
    return (
      <div className="px-4 min-h-[60vh] flex items-center justify-center">
        <p className="text-display animate-pulse">Curating your profile…</p>
      </div>
    );
  }

  return (
    <div className="px-4 mt-6">
      <div>
        <SectionTitle aside={`${images.length} images · click one to add detail`}>Your references</SectionTitle>
        <div className="flex gap-4 mb-4">
          <UploadButton label="+ Outfits" onFiles={(f) => upload(f, "outfit")} />
          <UploadButton label="+ Pieces" onFiles={(f) => upload(f, "item")} />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {images.map((image, i) => (
            <ImageTile key={image.id} image={image} index={i + 1} onOpen={() => setNoteFor(image)} />
          ))}
        </div>
        {images.length > 0 && (
          <button onClick={build} className="rule-t rule-b text-display py-2 w-full mt-6">
            {profile.version ? "Rebuild taste profile" : "Build taste profile"}
          </button>
        )}
        {profile.version > 0 && (
          <Link href="/taste" className="label underline block text-right mt-2">Open your moodboard →</Link>
        )}
      </div>

      {error && <p className="text-sm mt-3">{error}</p>}

      <Drawer open={!!noteFor} onClose={() => setNoteFor(null)}>
        {noteFor && (
          <NoteEditor
            image={noteFor}
            onSave={async (note) => {
              await run(async () => {
                await api.setNote(noteFor.id, note);
                return refresh();
              });
              setNoteFor(null);
            }}
            onDelete={async () => {
              await run(async () => {
                await api.deleteImage(noteFor.id);
                return refresh();
              });
              setNoteFor(null);
            }}
          />
        )}
      </Drawer>
    </div>
  );
}

function UploadButton({ label, onFiles }: { label: string; onFiles: (files: FileList | null) => void }) {
  return (
    <label className="label border border-ink px-3 py-2 cursor-pointer">
      {label}
      <input type="file" accept="image/*" multiple className="sr-only" onChange={(e) => onFiles(e.target.files)} />
    </label>
  );
}
