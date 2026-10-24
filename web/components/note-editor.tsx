"use client";

import { useRef, useState } from "react";
import { useAssistant, useAssistantSkill } from "@/lib/assistant";
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
  const latest = useRef(note);
  latest.current = note;
  const assistant = useAssistant();
  // While this photo is open, what the shopper tells the assistant becomes its note.
  useAssistantSkill({
    id: "note",
    label: "Noting what you like about this photo",
    intro: "Ooh, this one. What do you like about it?",
    placeholder: "I like the color, not the frills",
    async handle(text) {
      if (/^\s*(save|done|that'?s (it|all))\b/i.test(text)) {
        onSave(latest.current);
        return "Saved!";
      }
      const next = `${latest.current} ${text}`.trim();
      latest.current = next;
      setNote(next);
      return "Got it, added to the note. Say save when you're done.";
    },
  });
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
      {assistant.mode === "off" && (
        <button type="button" onClick={() => assistant.start("voice")} className="label underline justify-self-start">
          Say it out loud
        </button>
      )}
      {hint && <p className="text-xs text-muted">{hint}</p>}
      <div className="flex justify-between">
        {onDelete ? <button onClick={onDelete} className="label underline">Remove image</button> : <span />}
        <button onClick={() => onSave(note)} className="rule-t rule-b text-display px-2">Save</button>
      </div>
    </div>
  );
}
