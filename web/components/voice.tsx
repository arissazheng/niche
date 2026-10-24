"use client";

// Voice seam — owned by the voice engineer (see docs/WORKPLAN.md).
// The bake-off swaps the provider behind this interface; pages only depend on onTranscript.
// TODO(voice): implement Cartesia and Moss providers. API keys stay on the backend; the browser
// should receive a short-lived session token from a backend route.

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

const provider = process.env.NEXT_PUBLIC_VOICE_PROVIDER as VoiceProvider | undefined;

export function VoiceButton({ label = "Talk", context }: VoiceProps) {
  const ready = false; // flip once a provider is wired up
  return (
    <button
      type="button"
      disabled={!ready}
      title={ready ? undefined : `Voice (${provider ?? "provider not chosen"}) not wired yet — ${context}`}
      className="label border border-ink px-3 py-2 disabled:text-muted disabled:border-muted"
    >
      ● {label}
    </button>
  );
}
