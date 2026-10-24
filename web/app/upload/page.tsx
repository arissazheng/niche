"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { BuildProgress } from "@/components/build-progress";
import { SectionTitle } from "@/components/chrome";
import { Drawer } from "@/components/drawer";
import { ImageTile } from "@/components/image-tile";
import { NoteEditor } from "@/components/note-editor";
import { api } from "@/lib/api";
import { getProfileId } from "@/lib/session";
import type { ImageKind, ImportJob, ProfileView, TasteImage } from "@/lib/types";

const SITE_NAMES = { pinterest: "Pinterest", instagram: "Instagram" };

export default function LookbookPage() {
  const [view, setView] = useState<ProfileView | null>(null);
  const [missing, setMissing] = useState(false);
  const [building, setBuilding] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [noteFor, setNoteFor] = useState<TasteImage | null>(null);
  const [imports, setImports] = useState<ImportJob[]>([]);
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
    api.imports(id).then(setImports, () => setImports([]));
  }, [run]);

  // While an import runs in the background, check on it and pull in its photos when it finishes.
  const profileId = view?.profile.id;
  const importing = imports.some((x) => x.status === "running");
  useEffect(() => {
    if (!profileId || !importing) return;
    const timer = setInterval(async () => {
      const next = await api.imports(profileId).catch(() => null);
      if (!next) return;
      setImports(next);
      if (!next.some((x) => x.status === "running")) run(() => api.getProfile(profileId));
    }, 3000);
    return () => clearInterval(timer);
  }, [profileId, importing, run]);

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
  const notes = profile.lookbook_notes ?? [];
  const refresh = () => api.getProfile(id);

  async function upload(files: File[], kind: ImageKind) {
    const photos = files.filter((f) => f.type.startsWith("image/"));
    if (!photos.length) return setError("Those weren't photos. Drop JPG, PNG or HEIC images.");
    setUploading(photos.length);
    await run(async () => {
      for (const file of photos) await api.uploadImage(id, file, kind);
      return refresh();
    });
    setUploading(0);
  }

  async function startImport(url: string) {
    setError(null);
    try {
      const job = await api.importLink(id, url);
      setImports((list) => [job, ...list]);
      return true;
    } catch (err) {
      setError((err as Error).message);
      return false;
    }
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
        <p className="text-display animate-pulse"><BuildProgress profileId={id} /></p>
      </div>
    );
  }

  const count = `${images.length} photo${images.length === 1 ? "" : "s"}` + (notes.length ? ` · ${notes.length} note${notes.length === 1 ? "" : "s"}` : "");
  return (
    <div className="px-4 mt-6 grid gap-8">
      <section>
        <SectionTitle aside={count}>Your lookbook</SectionTitle>
        <p className="text-sm max-w-xl mb-4">
          Collect looks you love, from anywhere. Photos, a Pinterest board, an Instagram you admire, or just a few words.
          We build your taste profile from all of it.
        </p>
        <div className="grid gap-4 lg:grid-cols-3">
          <DropZone uploading={uploading} onFiles={upload} />
          <ImportBox jobs={imports} onImport={startImport} />
          <NotesBox notes={notes} onChange={(next) => run(() => api.setLookbookNotes(id, next))} />
        </div>
        {error && <p className="text-sm mt-3" role="alert">{error}</p>}
      </section>

      {images.length > 0 && (
        <section>
          <SectionTitle aside="Tap a photo to say what you like · × to remove">Saved looks</SectionTitle>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
            {images.map((image, i) => (
              <ImageTile
                key={image.id}
                image={image}
                index={i + 1}
                onOpen={() => setNoteFor(image)}
                onRemove={() => run(async () => { await api.deleteImage(image.id); return refresh(); })}
              />
            ))}
          </div>
        </section>
      )}

      {(images.length > 0 || notes.length > 0) && (
        <section>
          <button onClick={build} disabled={importing || uploading > 0} className="rule-t rule-b text-display py-2 w-full disabled:text-muted">
            {importing ? "Waiting for your import…" : profile.version ? "Rebuild my taste profile" : "Build my taste profile"}
          </button>
          {profile.version > 0 && (
            <Link href="/taste" className="label underline block text-right mt-2">Open your moodboard →</Link>
          )}
        </section>
      )}

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

function DropZone({ uploading, onFiles }: { uploading: number; onFiles: (files: File[], kind: ImageKind) => void }) {
  const [over, setOver] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const own = useRef<HTMLInputElement>(null);
  const files = (list: FileList | null) => Array.from(list ?? []);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        onFiles(files(e.dataTransfer.files), "outfit");
      }}
      className={`border border-dashed border-ink p-4 flex flex-col gap-3 justify-between min-h-56 ${over ? "bg-plinth" : ""}`}
    >
      <div>
        <p className="text-display">{uploading ? `Adding ${uploading} photo${uploading === 1 ? "" : "s"}…` : "Drop photos here"}</p>
        <p className="text-sm mt-1">Screenshots, saved posts, anything with an outfit you love.</p>
      </div>
      <button type="button" onClick={() => picker.current?.click()} className="label bg-ink text-paper px-3 py-2 self-start">
        + Add to my lookbook
      </button>
      <p className="text-sm">
        Got photos of you in outfits you love?{" "}
        <button type="button" onClick={() => own.current?.click()} className="underline">Add your own fits</button>.
        They&apos;re the best clue to what you actually wear.
      </p>
      <input ref={picker} type="file" accept="image/*" multiple className="sr-only" onChange={(e) => onFiles(files(e.target.files), "outfit")} />
      <input ref={own} type="file" accept="image/*" multiple className="sr-only" onChange={(e) => onFiles(files(e.target.files), "own")} />
    </div>
  );
}

function ImportBox({ jobs, onImport }: { jobs: ImportJob[]; onImport: (url: string) => Promise<boolean> }) {
  const [url, setUrl] = useState("");
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (url.trim() && (await onImport(url.trim()))) setUrl("");
      }}
      className="border border-ink p-4 flex flex-col gap-3 min-h-56"
    >
      <p className="text-display">Import from Pinterest or Instagram</p>
      <input
        className="input"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="pinterest.com/you/your-board"
        aria-label="Pinterest or Instagram link"
      />
      <button type="submit" className="label border border-ink px-3 py-2 self-start">Import</button>
      <p className="text-sm">
        The board or profile must be public. Secret boards and private accounts can&apos;t be read.
        From Instagram we only keep the outfit photos, never who posted them.
      </p>
      {jobs.slice(0, 3).map((job) => (
        <p key={job.id} className={`text-sm ${job.status === "running" ? "animate-pulse" : ""}`} role="status">
          {job.status === "running"
            ? `Importing from ${SITE_NAMES[job.site]}… this takes 1–3 minutes. You can keep adding looks.`
            : job.message}
        </p>
      ))}
    </form>
  );
}

function NotesBox({ notes, onChange }: { notes: string[]; onChange: (notes: string[]) => void }) {
  const [draft, setDraft] = useState("");
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!draft.trim()) return;
        onChange([...notes, draft.trim()]);
        setDraft("");
      }}
      className="border border-ink p-4 flex flex-col gap-3 min-h-56"
    >
      <p className="text-display">Can&apos;t find the right pic?</p>
      <textarea
        className="input min-h-20"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        placeholder="Leave a short note of what you're thinking, like “a cropped brown leather jacket, a bit 70s”"
        aria-label="Describe a look"
      />
      <button type="submit" className="label border border-ink px-3 py-2 self-start">Add note</button>
      {notes.length > 0 && (
        <ul className="grid gap-1">
          {notes.map((note) => (
            <li key={note} className="text-sm flex justify-between gap-2">
              <span>“{note}”</span>
              <button type="button" onClick={() => onChange(notes.filter((n) => n !== note))} aria-label="Remove note" className="label">
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </form>
  );
}
