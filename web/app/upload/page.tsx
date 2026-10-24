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

const SITE_NAMES = { pinterest: "Pinterest", instagram: "Instagram", tiktok: "TikTok" };
const URLS = /(?:https?:\/\/)?(?:[\w-]+\.)*(?:pinterest\.[a-z.]+|pin\.it|instagram\.com|tiktok\.com)\/[^\s,]*/gi;

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

  // ⌘V anywhere on the page: pasted images are added, pasted Pinterest/Instagram/TikTok links are imported.
  const onPaste = useRef<(e: ClipboardEvent) => void>(() => {});
  useEffect(() => {
    const handler = (e: ClipboardEvent) => onPaste.current(e);
    window.addEventListener("paste", handler);
    return () => window.removeEventListener("paste", handler);
  }, []);

  // While an import runs in the background, check on it and pull in its photos when it finishes.
  const profileId = view?.profile.id;
  const importing = imports.some((x) => x.status === "running");
  useEffect(() => {
    if (!profileId || !importing) return;
    const timer = setInterval(async () => {
      const next = await api.imports(profileId).catch(() => null);
      if (!next) return;
      setImports((before) => {
        // Show each import's photos as soon as it finishes, not only when the last one does.
        const finished = next.some((x) => x.status !== "running" && before.find((b) => b.id === x.id)?.status === "running");
        if (finished) run(() => api.getProfile(profileId));
        return next;
      });
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

  // Takes one link or several (pasted together); each runs as its own background import.
  async function startImport(text: string) {
    setError(null);
    const links = text.match(URLS) ?? [text.trim()];
    const errors: string[] = [];
    for (const link of links) {
      try {
        const job = await api.importLink(id, link);
        setImports((list) => [job, ...list]);
      } catch (err) {
        errors.push((err as Error).message);
      }
    }
    if (errors.length) setError([...new Set(errors)].join(" "));
    return errors.length < links.length;
  }

  onPaste.current = (e: ClipboardEvent) => {
    const files = Array.from(e.clipboardData?.files ?? []).filter((f) => f.type.startsWith("image/"));
    if (files.length) {
      e.preventDefault();
      upload(files, "outfit");
      return;
    }
    const target = e.target as HTMLElement | null;
    if (target?.closest("input, textarea")) return; // typing a link or note: leave it alone
    const text = e.clipboardData?.getData("text") ?? "";
    if (text.match(URLS)) {
      e.preventDefault();
      startImport(text);
    }
  };

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
          Collect looks you love, from anywhere: photos, a Pinterest board, Instagram posts, TikToks, or just a few
          words. Tip: copy an image or a link anywhere and press ⌘V on this page.
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
      <p className="text-display">Import from Pinterest, Instagram or TikTok</p>
      <textarea
        className="input min-h-12"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Paste a board, pin, post, reel, TikTok or profile link. Several at once is fine."
        aria-label="Pinterest, Instagram or TikTok links"
      />
      <button type="submit" className="label border border-ink px-3 py-2 self-start">Import</button>
      <p className="text-sm">
        Links must be public. Secret boards and private accounts can&apos;t be read. We only keep the outfit photos
        (for TikToks, a few frames), never who posted them.
      </p>
      {jobs.slice(0, 3).map((job) => (
        <p key={job.id} className={`text-sm ${job.status === "running" ? "animate-pulse" : ""}`} role="status">
          {job.status === "running"
            ? `Importing from ${SITE_NAMES[job.site]}… ${job.kind === "post" ? "usually under a minute" : "profiles and boards can take a few minutes"}. You can keep adding looks.`
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
