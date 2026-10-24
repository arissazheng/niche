"use client";

import { useState } from "react";
import { VoiceButton } from "@/components/voice";
import type { TasteImage } from "@/lib/types";

/** Per-image preference note ("I like the color, not the frills"), shared by Upload and the moodboard. */
export function NoteEditor({
  image,
  onSave,
  onDelete,
  hint,
}: {
  image: TasteImage;
  onSave: (note: string) => void;
  onDelete?: () => void;
  hint?: string;
}) {
  const [note, setNote] = useState(image.note);
  return (
    <div className="grid gap-3">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={image.url} alt="" className="bg-plinth w-full h-[40dvh] object-contain" />
      <p className="text-display">What do you like about this?</p>
      <textarea
        className="input min-h-24"
        placeholder="I like the color, not the frills"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <VoiceButton context="profile-review" label="Say it" onTranscript={(t) => setNote((n) => `${n} ${t}`.trim())} />
      {hint && <p className="text-xs text-muted">{hint}</p>}
      <div className="flex justify-between">
        {onDelete ? <button onClick={onDelete} className="label underline">Remove image</button> : <span />}
        <button onClick={() => onSave(note)} className="rule-t rule-b text-display px-2">Save</button>
      </div>
    </div>
  );
}
