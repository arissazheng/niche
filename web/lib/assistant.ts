// The Niche assistant: one conversation that follows the shopper across every page, by voice or by text.
// Pages teach it what to do with what it hears by registering a skill (fill in the profile form, edit the taste
// profile, write an image note). Anything no page claims goes to the shopping agent (POST /chat).

import { createContext, useContext, useEffect, useRef } from "react";
import type { Budget, ChatTurn } from "./types";

export interface Skill {
  /** "onboarding", "profile", "note"… One registration per id. */
  id: string;
  /** What the assistant is helping with here, shown in the dock. */
  label: string;
  /** Said once per visit, when the conversation reaches this page. */
  intro?: string;
  placeholder?: string;
  /** The reply to say, or null to pass the message on to the shopping agent. */
  handle(text: string): Promise<string | null>;
}

export type Mode = "off" | "voice" | "text";
export type Phase = "idle" | "listening" | "hearing" | "thinking" | "speaking";

/** A turn in the conversation; `skill` says which page handled it ("shop" for the shopping agent). `aside` marks
 * something the assistant brought up on its own (left out of the shopping agent's history); `done` marks the line
 * announcing a finished search. */
export type Turn = ChatTurn & { skill: string; aside?: boolean; done?: boolean };

export interface ShopState {
  profileId: string | null;
  searchId: string | null;
  /** True while a search started in this visit hasn't been announced yet. */
  fresh: boolean;
  budget: Budget | null;
  keepToBudget: boolean;
  setKeepToBudget(on: boolean): void;
  refreshBudget(): void;
  /** "Yes, search": runs an offered search as-is. */
  accept(proposal: ChatTurn): void;
  reset(): void;
  /** The shop page tells the assistant a search finished, so it can say so. */
  announce(searchId: string, text: string): void;
}

export interface Assistant {
  turns: Turn[];
  mode: Mode;
  phase: Phase;
  error: string | null;
  skill: Pick<Skill, "id" | "label" | "placeholder">;
  start(mode: Exclude<Mode, "off">): void;
  stop(): void;
  send(text: string): void;
  /** Something the assistant brings up on its own (a reaction to new photos, a read-back of the moodboard): spoken
   * in a voice conversation, otherwise shown as a nudge by the dock. */
  say(text: string): void;
  /** What to say back, in the assistant's own words: `facts` is what happened and what to ask next; `fallbacks` are
   * the page's own lines, used without Claude. */
  phrase(facts: string, fallbacks: string[]): Promise<string>;
  /** The latest thing it brought up while the conversation was closed, until the shopper opens it. */
  nudge: string | null;
  /** Hide the nudge bubble (the × on it). */
  dismissNudge: () => void;
  /** Cuts the assistant off mid-sentence and listens. */
  interrupt(): void;
  level(): number;
  /** The picked voice (a key from GET /v1/voice/voices), or null for the default. */
  voice: string | null;
  setVoice(key: string, name: string): void;
  register(skill: Skill): () => void;
  shop: ShopState;
}

export const AssistantContext = createContext<Assistant | null>(null);

export function useAssistant(): Assistant {
  const assistant = useContext(AssistantContext);
  if (!assistant) throw new Error("useAssistant outside AssistantProvider");
  return assistant;
}

/** Lets this page handle what the shopper says while it is open. `handle` may change every render. */
export function useAssistantSkill(skill: Skill | null) {
  const { register } = useAssistant();
  const latest = useRef(skill);
  latest.current = skill;
  const id = skill?.id;
  const intro = skill?.intro;
  const label = skill?.label;
  const placeholder = skill?.placeholder;
  useEffect(() => {
    if (!id) return;
    return register({
      id,
      label: label ?? "",
      intro,
      placeholder,
      handle: (text) => latest.current?.handle(text) ?? Promise.resolve(null),
    });
  }, [id, intro, label, placeholder, register]);
}

/** A short "no" / "that's it": the shopper is done here, not asking for a change. */
export const isNo = (text: string) =>
  text.trim().split(/\s+/).length <= 5 &&
  /^\s*(no|nope|nah|not really|nothing( else)?|i'?m good|i'?m (all )?set|that'?s (it|all|everything)|all good|we'?re good|done)\b/i.test(text);

/** A short "yes". */
export const isYes = (text: string) =>
  text.trim().split(/\s+/).length <= 6 && /^\s*(yes|yeah|yep|yup|sure|ok(ay)?|go( ahead)?|do it|please|let'?s do it|build)\b/i.test(text);

/** Shopping requests, which go to the shopping agent even from a page that handles other things. */
export const SHOPPING = /\b(find|search|look(ing)? for|show me|shop(ping)? for|buy|need (a|an|some)|want (a|an|some))\b/i;

const EDITABLE = "input, textarea, select, [contenteditable=''], [contenteditable='true']";

/** True when a keypress belongs to a text field rather than the page. */
export function isTyping(target: EventTarget | null) {
  return target instanceof Element && !!target.closest(EDITABLE);
}

/** Detects two taps of the space bar within `windowMs`; any other key in between starts over. */
export function doubleSpace(windowMs = 400) {
  let last = 0;
  return (e: Pick<KeyboardEvent, "key" | "repeat" | "metaKey" | "ctrlKey" | "altKey" | "shiftKey" | "target" | "timeStamp">) => {
    if (e.key !== " " || e.repeat || e.metaKey || e.ctrlKey || e.altKey || e.shiftKey || isTyping(e.target)) {
      last = 0;
      return false;
    }
    if (last && e.timeStamp - last <= windowMs) {
      last = 0;
      return true;
    }
    last = e.timeStamp;
    return false;
  };
}
