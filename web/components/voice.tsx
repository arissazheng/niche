"use client";

// Voice seam (see docs/WORKPLAN.md). Pages only depend on onTranscript.
// Push to talk: click to record, click again to stop. The recording goes to the backend (POST /v1/voice/transcribe),
// which sends it to Cartesia speech-to-text with the server's key, so the browser never holds a key or token.

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

export type VoiceProvider = "cartesia" | "moss";

export interface VoiceSession {
  stop(): void;
}

export interface VoiceProps {
  /** Final user utterance, e.g. "make it less minimal, more vintage". */
  onTranscript: (text: string) => void;
  /** What the agent should focus on: onboarding questions, profile review, or shopping chat. */
  context: "onboarding" | "profile-review" | "shop";
  label?: string;
}

// Cartesia won the bake-off: Moss is semantic search, not speech-to-text.
const provider = (process.env.NEXT_PUBLIC_VOICE_PROVIDER || "cartesia") as VoiceProvider;
const MAX_SECONDS = 60;

type State = "idle" | "listening" | "hearing";

function recorderType() {
  // Chrome/Firefox record webm/ogg opus, Safari records mp4; Cartesia reads all three.
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];
  return types.find((t) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) ?? "";
}

/** Records one utterance from the mic. stop() ends it; the promise resolves with the audio. */
async function record(onStart: () => void): Promise<{ session: VoiceSession; audio: Promise<Blob> }> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  const type = recorderType();
  const recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
  const chunks: Blob[] = [];
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const audio = new Promise<Blob>((resolve) => {
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      resolve(new Blob(chunks, { type: recorder.mimeType || type || "audio/webm" }));
    };
  });
  recorder.start();
  onStart();
  const limit = setTimeout(() => recorder.state === "recording" && recorder.stop(), MAX_SECONDS * 1000);
  return {
    session: {
      stop() {
        clearTimeout(limit);
        if (recorder.state === "recording") recorder.stop();
      },
    },
    audio,
  };
}

export function VoiceButton({ label = "Talk", context, onTranscript }: VoiceProps) {
  const [state, setState] = useState<State>("idle");
  const [error, setError] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);
  const session = useRef<VoiceSession | null>(null);
  const deliver = useRef(onTranscript);
  deliver.current = onTranscript;

  useEffect(() => {
    setSupported(typeof window !== "undefined" && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined");
    return () => session.current?.stop();
  }, []);

  const ready = provider === "cartesia" && supported;

  async function toggle() {
    if (state === "listening") {
      session.current?.stop();
      return;
    }
    if (state !== "idle") return;
    setError(null);
    try {
      const { session: s, audio } = await record(() => setState("listening"));
      session.current = s;
      const blob = await audio;
      session.current = null;
      setState("hearing");
      const { text } = await api.transcribe(blob);
      if (text) deliver.current(text);
      else setError("Didn’t catch that. Try again?");
    } catch (err) {
      const e = err as Error;
      setError(e.name === "NotAllowedError" ? "Allow the microphone to talk." : e.message);
    } finally {
      session.current = null;
      setState("idle");
    }
  }

  const text = state === "listening" ? "■ Stop" : state === "hearing" ? "Listening…" : `● ${label}`;
  const hint = !ready
    ? !supported
      ? "This browser can’t record audio"
      : `Voice provider "${provider}" is not supported; use cartesia`
    : state === "listening"
      ? "Recording: click to stop"
      : `Talk (${context})`;

  return (
    <span className="inline-grid gap-1 justify-items-start">
      <button
        type="button"
        onClick={toggle}
        disabled={!ready || state === "hearing"}
        title={hint}
        aria-pressed={state === "listening"}
        className={`label border px-3 py-2 disabled:text-muted disabled:border-muted ${
          state === "listening" ? "border-ink bg-ink text-paper animate-pulse" : "border-ink"
        }`}
      >
        {text}
      </button>
      {error && (
        <span className="text-xs text-muted max-w-56" role="status">
          {error}
        </span>
      )}
    </span>
  );
}
