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
import { SHOPPING, useAssistant, useAssistantSkill } from "@/lib/assistant";
import { getProfileId } from "@/lib/session";
import type { ImageKind, ImportJob, ProfileView, TasteImage } from "@/lib/types";

const SITE_NAMES = { pinterest: "Pinterest", instagram: "Instagram", tiktok: "TikTok" };
const IMAGE_URL = /^https?:\/\/\S+\.(?:jpe?g|png|webp|gif|avif)(?:[?#]\S*)?$/i;
const URLS = /(?:https?:\/\/)?(?:[\w-]+\.)*(?:pinterest\.[a-z.]+|pin\.it|instagram\.com|tiktok\.com)\/[^\s,]*/gi;

export default function LookbookPage() {
  const [view, setView] = useState<ProfileView | null>(null);
  const [missing, setMissing] = useState(false);
  const [building, setBuilding] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [buildError, setBuildError] = useState<string | null>(null);
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

  // Ctrl+V / ⌘V anywhere on the page: pasted images are added, pasted Pinterest/Instagram/TikTok links are imported.
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

  // The assistant reacts to new photos like a friend would ("ooh, I'm sensing a 90s minimal thing").
  const { say } = useAssistant();
  const seen = useRef<Set<string> | null>(null);
  const imageIds = view?.images.map((x) => x.id).join(",") ?? "";
  useEffect(() => {
    if (!profileId || !imageIds) return;
    const ids = imageIds.split(",");
    const added = seen.current ? ids.filter((x) => !seen.current!.has(x)) : [];
    seen.current = new Set(ids);
    if (added.length) api.reactToPhotos(profileId, added.slice(-4)).then(({ text }) => say(text), () => {});
  }, [profileId, imageIds, say]);

  // Talking here: describe a look to save it as a note, or say you're done to build the profile.
  const actions = useRef<{ note: (text: string) => Promise<void>; build: () => void }>({ note: async () => {}, build: () => {} });
  useAssistantSkill(
    view
      ? {
          id: "lookbook",
          label: "Building your lookbook",
          intro: view.images.length
            ? "Add a few more looks you love, or tell me about one in words. Say build when you're ready."
            : "Now show me your style! Drop in photos of outfits you love, or just describe a look and I'll note it.",
          placeholder: "I love oversized blazers with baggy jeans",
          async handle(text) {
            if (SHOPPING.test(text)) return null;
            if (/^\s*(build|done|i'?m done|that'?s (it|all)|finish|ready|let'?s (go|see))\b/i.test(text)) {
              actions.current.build();
              return "Ooh, exciting. Building your taste profile now, give me a sec!";
            }
            await actions.current.note(text);
            return "Love it, noted! I'll use that when I build your profile. Anything else?";
          },
        }
      : null,
  );

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

  /** Resolves to how many photos were added. */
  async function upload(files: File[], kind: ImageKind) {
    const photos = files.filter((f) => f.type.startsWith("image/"));
    if (!photos.length) {
      setError("Those weren't photos. Add JPG, PNG or HEIC images.");
      return 0;
    }
    setUploading(photos.length);
    const failed = await run(async () => {
      for (const file of photos) await api.uploadImage(id, file, kind);
      return refresh();
    });
    setUploading(0);
    return failed ? 0 : photos.length;
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

  // Images pasted or dragged in from a web page often arrive as an address (or inline data), not a file.
  async function addFromWeb(urls: string[]) {
    setError(null);
    let added = 0;
    const errors: string[] = [];
    setUploading(urls.length);
    for (const url of urls) {
      try {
        if (url.startsWith("data:image/")) {
          const blob = await (await fetch(url)).blob();
          await api.uploadImage(id, new File([blob], "pasted-image", { type: blob.type }), "outfit");
        } else {
          await api.imageFromUrl(id, url);
        }
        added++;
      } catch (err) {
        errors.push((err as Error).message);
      }
    }
    setUploading(0);
    if (added) await run(refresh); // before the messages: run() clears the error line
    if (errors.length) setError([...new Set(errors)].join(" "));
  }

  /** Everything a paste or a drop can carry: image files, web images, Pinterest/Instagram/TikTok links. */
  function take(data: DataTransfer | null, verb: "pasted" | "dropped", typing = false) {
    if (!data) return false;
    const files = Array.from(data.files).filter((f) => f.type.startsWith("image/"));
    if (files.length) {
      upload(files, "outfit");
      return true;
    }
    if (typing) return false; // pasting text into the link or note box: leave it alone
    const html = data.getData("text/html");
    const images = [...html.matchAll(/<img[^>]+src="([^"]+)"/gi)].map((m) => m[1].replace(/&amp;/g, "&"))
      .filter((src) => /^(https?:|data:image\/)/.test(src));
    const text = data.getData("text/uri-list") || data.getData("text/plain") || "";
    const links = text.match(URLS);
    if (links) {
      startImport(text);
      return true;
    }
    const direct = text.split(/\s+/).filter((u) => IMAGE_URL.test(u) || (verb === "dropped" && /^https?:\/\//.test(u)));
    const web = [...new Set([...images, ...direct])].slice(0, 12);
    if (web.length) {
      addFromWeb(web);
      return true;
    }
    return false;
  }

  onPaste.current = (e: ClipboardEvent) => {
    // The target is whatever has focus, which may be the page itself rather than an element.
    const typing = e.target instanceof Element && !!e.target.closest("input, textarea");
    if (take(e.clipboardData, "pasted", typing)) e.preventDefault();
  };

  // Build errors show next to the button, not at the top of the page where they'd be missed.
  async function build() {
    if (view?.up_to_date) return router.push("/taste"); // nothing changed since the last build
    setBuildError(null);
    setBuilding(true);
    try {
      await api.build(id);
      router.push("/taste");
    } catch (err) {
      setBuildError((err as Error).message);
      setBuilding(false);
    }
  }

  actions.current = {
    note: async (text) => void (await run(() => api.setLookbookNotes(id, [...notes, text.slice(0, 300)].slice(-20)))),
    build,
  };

  const consented = !!profile.onboarding.data_consent;
  const setConsent = (data_consent: boolean) =>
    run(() => api.updateOnboarding(id, { ...profile.onboarding, data_consent }));

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
          words.
        </p>
        <div className="grid gap-4 lg:grid-cols-3">
          <DropZone uploading={uploading} onFiles={upload} onDrop={(data) => take(data, "dropped")} />
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
        <section className="grid gap-3">
          {!consented && (
            <label className="flex items-start gap-3 text-sm">
              <input type="checkbox" className="mt-1 accent-ink" checked={consented} onChange={(e) => setConsent(e.target.checked)} />
              <span>
                I agree that my photos and notes are sent to Claude (Anthropic) to build my taste profile. My name, email
                and age never are. <Link href="/how-it-works#data" className="underline">What Niche keeps</Link>
              </span>
            </label>
          )}
          <button
            onClick={build}
            disabled={!consented || importing || uploading > 0}
            className="rule-t rule-b text-display py-2 w-full disabled:text-muted"
          >
            {importing
              ? "Waiting for your import…"
              : view.up_to_date
                ? "View my taste profile"
                : profile.version
                  ? "Rebuild my taste profile"
                  : "Build my taste profile"}
          </button>
          {buildError && <p className="text-sm" role="alert">{buildError}</p>}
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

function DropZone({
  uploading,
  onFiles,
  onDrop,
}: {
  uploading: number;
  onFiles: (files: File[], kind: ImageKind) => void;
  onDrop: (data: DataTransfer) => boolean;
}) {
  const [over, setOver] = useState(false);
  const [mac, setMac] = useState(false);
  useEffect(() => setMac(/Mac|iPhone|iPad/.test(navigator.userAgent)), []);
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
        // Files from the computer, or an image dragged straight from another browser tab.
        onDrop(e.dataTransfer);
      }}
      className={`border border-dashed border-ink p-4 flex flex-col gap-3 justify-between min-h-56 ${over ? "bg-plinth" : ""}`}
    >
      <div>
        <p className="text-display">{uploading ? `Adding ${uploading} photo${uploading === 1 ? "" : "s"}…` : "Paste or drop photos here"}</p>
        <p className="text-sm mt-1">
          See a look you love online? Copy the image and press{" "}
          <kbd className="label border border-ink px-1">{mac ? "⌘V" : "Ctrl+V"}</kbd> anywhere on this page. No need to
          download it. Screenshots work too.
        </p>
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
      {/* Finished imports speak for themselves (the photos appear below); only progress and problems get a line. */}
      {jobs.filter((job) => job.status !== "done").slice(0, 3).map((job) => (
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
