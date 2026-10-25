"use client";

// The Niche assistant: mounted once in the layout, so one conversation follows the shopper from page to page.
// Voice is hands-free: once started the mic stays open, each pause sends what was said, and the reply is spoken
// back (Cartesia both ways, through the backend). Text is the same conversation, typed. Pages add what they can do
// with useAssistantSkill (lib/assistant.ts); everything else goes to the shopping agent, whose results show on /shop.

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import {
  AssistantContext,
  doubleSpace,
  useAssistant,
  type Assistant,
  type Mode,
  type Phase,
  type ShopState,
  type Skill,
  type Turn,
} from "@/lib/assistant";
import { getProfileId } from "@/lib/session";
import type { Budget, ChatTurn } from "@/lib/types";
import { canListen, openMic, type Mic } from "@/lib/voice-loop";

const SHOP_SKILL = { id: "shop", label: "Shopping with you", placeholder: "A vintage leather jacket under $150" };
const SHOP_INTRO = "Hey, it's Niche! What are we shopping for today?";
const STARTERS = ["Find me black knee-high boots under $120", "Find me a vintage leather jacket", "I need an outfit for a wedding"];
const FOLLOW_UPS = ["Compare number 1 and 2", "Which is the best value?", "Which fits my style best?"];
// Whisper hears these in room noise; nobody means them as a whole message.
const NOISE = /^\s*(you|\.+|thank you\.?|thanks for watching!?|thank you for watching\.?|bye\.?)\s*$/i;

interface Thread {
  messages: ChatTurn[];
  searchId: string | null;
}

// The shopping conversation is a per-browser convenience; searches themselves live on the server.
function loadThread(profileId: string): Thread {
  try {
    const saved = JSON.parse(localStorage.getItem(`shop-chat:${profileId}`) ?? "null") as Thread | null;
    if (saved && Array.isArray(saved.messages)) return saved;
  } catch {
    // Unreadable or blocked storage: start a fresh conversation.
  }
  return { messages: [], searchId: null };
}

function saveThread(profileId: string, thread: Thread) {
  try {
    localStorage.setItem(`shop-chat:${profileId}`, JSON.stringify(thread));
  } catch {
    // Storage blocked: the thread just won't survive a reload.
  }
}

const pick = <T,>(items: T[]) => items[Math.floor(Math.random() * items.length)];

/** The shopping agent's history: its own turns, without the assistant's bookkeeping. */
function shopTurns(turns: Turn[]): ChatTurn[] {
  return turns
    .filter((t) => t.skill === "shop" && !t.aside)
    .map((t) => {
      const turn: Partial<Turn> = { ...t };
      delete turn.skill;
      delete turn.aside;
      delete turn.done;
      return turn as ChatTurn;
    });
}

export function AssistantProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [mode, setModeState] = useState<Mode>("off");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [nudge, setNudge] = useState<string | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [searchId, setSearchIdState] = useState<string | null>(null);
  const [freshId, setFreshId] = useState<string | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [keepToBudget, setKeep] = useState(false);

  // Async work reads the latest values through refs: a reply can land after several renders.
  const turnsRef = useRef(turns);
  const modeRef = useRef(mode);
  const skillsRef = useRef(skills);
  const profileRef = useRef(profileId);
  const searchRef = useRef(searchId);
  const keepRef = useRef(keepToBudget);
  const pathRef = useRef(pathname);
  pathRef.current = pathname;
  keepRef.current = keepToBudget;
  const mic = useRef<Mic | null>(null);
  const busy = useRef(false);
  const speaking = useRef(Promise.resolve());
  const queued = useRef(0);
  const introduced = useRef(new Set<string>());

  const setMode = (next: Mode) => {
    modeRef.current = next;
    setModeState(next);
  };

  const commit = useCallback((next: Turn[]) => {
    turnsRef.current = next;
    setTurns(next);
    const id = profileRef.current;
    if (id) saveThread(id, { messages: shopTurns(next), searchId: searchRef.current });
  }, []);

  const add = useCallback((turn: Turn) => commit([...turnsRef.current, turn]), [commit]);

  const setSearch = useCallback((id: string | null, fresh = false) => {
    searchRef.current = id;
    setSearchIdState(id);
    if (fresh) setFreshId(id);
  }, []);

  const top = () => skillsRef.current.at(-1) ?? null;

  // The current profile, and its shopping thread, follow the page: onboarding creates one, a friend link swaps it.
  useEffect(() => {
    const id = getProfileId();
    if (id === profileRef.current) return;
    profileRef.current = id;
    setProfileId(id);
    const thread = id ? loadThread(id) : { messages: [], searchId: null };
    const others = turnsRef.current.filter((t) => t.skill !== "shop");
    turnsRef.current = [...thread.messages.map((m) => ({ ...m, skill: "shop" })), ...others];
    setTurns(turnsRef.current);
    setSearch(thread.searchId);
    setBudget(null);
    if (id) api.budget(id).then(setBudget, () => setBudget(null));
  }, [pathname, setSearch]);

  useEffect(() => {
    try {
      setKeep(localStorage.getItem("keep-to-budget") === "1");
    } catch {
      // storage blocked: stays off
    }
  }, []);

  const listen = useCallback(() => {
    if (modeRef.current !== "voice" || !mic.current || busy.current || queued.current) return;
    setPhase("listening");
    mic.current.resume();
  }, []);

  /** Speaks in a voice conversation; lines queue so nothing talks over anything else. */
  const speak = useCallback(
    (text: string) => {
      if (modeRef.current !== "voice" || !mic.current) return Promise.resolve();
      queued.current++;
      mic.current.pause();
      const audio = api.speak(text, voiceRef.current); // start fetching now, play in turn
      speaking.current = speaking.current.then(async () => {
        try {
          const bytes = await audio;
          if (modeRef.current !== "voice" || !mic.current) return;
          setPhase("speaking");
          await mic.current.play(bytes);
        } catch (err) {
          setError(`Couldn’t speak: ${(err as Error).message}`);
        } finally {
          queued.current--;
          if (!queued.current && !busy.current) listen();
        }
      });
      return speaking.current;
    },
    [listen],
  );

  const closeMic = () => {
    mic.current?.close();
    mic.current = null;
  };

  // Shopping turns: the agent replies, offers a search, or starts one (whose results show on /shop).
  const shop = useCallback(
    async (): Promise<string> => {
      const id = getProfileId();
      if (!id) {
        introduced.current.add("onboarding");
        router.push("/onboard");
        return "Let's set up your profile first so I know your style. What's your name, and where do you usually shop?";
      }
      const reply = await api.chat(id, shopTurns(turnsRef.current), searchRef.current, keepRef.current);
      const turn: Turn = { role: "agent", text: reply.reply, skill: "shop" };
      if (reply.linked?.length) turn.linked = reply.linked;
      if (reply.recalled?.length) turn.recalled = reply.recalled;
      if (reply.action === "search") turn.brief = reply.brief;
      if (reply.action === "propose") {
        turn.proposed = reply.brief;
        turn.proposed_price = reply.max_item_price ?? null;
        turn.proposed_size = reply.size ?? null;
        turn.proposed_must_have = reply.must_have?.length ? reply.must_have : null;
        turn.proposed_category = reply.category ?? null;
        turn.proposed_brands = reply.brands?.length ? reply.brands : null;
      }
      if (reply.budget) setBudget({ linked: true, ...reply.budget });
      if (reply.search_id) setSearch(reply.search_id, true);
      add(turn);
      if (reply.search_id && pathRef.current !== "/shop") router.push("/shop");
      return reply.reply;
    },
    [add, router, setSearch],
  );

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busy.current) return;
      busy.current = true;
      mic.current?.pause();
      setError(null);
      setNudge(null);
      setPhase("thinking");
      const skill = top();
      const asked = turnsRef.current.length;
      add({ role: "user", text, skill: skill?.id ?? "shop" });
      let reply: string | null = null;
      try {
        reply = skill ? await skill.handle(text) : null;
        if (reply === null) {
          // Not for this page: hand it, and the message, to the shopping agent.
          if (skill) commit(turnsRef.current.map((t, i) => (i === asked ? { ...t, skill: "shop" } : t)));
          reply = await shop();
        } else add({ role: "agent", text: reply, skill: skill!.id });
      } catch (err) {
        setError((err as Error).message);
      } finally {
        busy.current = false;
        setPhase(modeRef.current === "voice" ? "listening" : "idle");
      }
      if (reply) speak(reply);
      else listen();
    },
    [add, commit, listen, shop, speak],
  );

  // A page's reply in the assistant's own words (backend /v1/voice/line), so it reacts to what was actually said and
  // doesn't repeat itself. Falls back to one of the page's own lines.
  const phrase = useCallback(async (facts: string, fallbacks: string[]) => {
    const recent = turnsRef.current.filter((t) => t.role === "agent").slice(-4).map((t) => t.text);
    const fresh = fallbacks.filter((f) => !recent.includes(f));
    const fallback = pick(fresh.length ? fresh : fallbacks);
    const heard = turnsRef.current.findLast((t) => t.role === "user")?.text ?? "";
    try {
      return (await api.line({ page: top()?.id ?? "shop", heard, facts, fallback, recent, profile_id: getProfileId() })).text;
    } catch {
      return fallback;
    }
  }, []);

  const say = useCallback(
    (text: string) => {
      add({ role: "agent", text, skill: top()?.id ?? "shop", aside: true });
      if (modeRef.current === "voice") speak(text);
      else if (modeRef.current === "off") setNudge(text);
    },
    [add, speak],
  );

  const heard = useCallback(
    async (wav: Blob) => {
      if (busy.current || queued.current) return;
      mic.current?.pause();
      setPhase("thinking");
      try {
        const { text } = await api.transcribe(wav);
        if (text && !NOISE.test(text)) return send(text);
      } catch (err) {
        const message = (err as Error).message;
        setError(message.startsWith("Voice is off") ? `${message}. You can type instead.` : `Didn’t catch that: ${message}`);
      }
      setPhase("listening");
      listen();
    },
    [listen, send],
  );

  const introduce = useCallback(
    (skill: Skill | null) => {
      const id = skill?.id ?? "shop";
      if (introduced.current.has(id)) return false;
      // On Shop the page itself already asks "what are you shopping for?".
      const intro = skill ? skill.intro : getProfileId() && pathRef.current !== "/shop" ? SHOP_INTRO : null;
      if (!intro) return false;
      introduced.current.add(id);
      say(intro);
      return true;
    },
    [say],
  );

  const start = useCallback(
    async (next: Exclude<Mode, "off">) => {
      setError(null);
      setNudge(null);
      if (next === "text") {
        closeMic();
        setMode("text");
        setPhase(busy.current ? "thinking" : "idle");
        if (!busy.current) introduce(top());
        return;
      }
      if (!canListen()) {
        setError("This browser can’t use the microphone here. Type instead.");
        setMode("text");
        return;
      }
      try {
        mic.current ??= await openMic({ onUtterance: heard, onSpeechStart: () => setPhase("hearing") });
      } catch (err) {
        const e = err as Error;
        setError(e.name === "NotAllowedError" ? "Allow the microphone to talk to Niche, or type instead." : e.message);
        setMode("text");
        return;
      }
      setMode("voice");
      if (!introduce(top())) listen();
    },
    [heard, introduce, listen],
  );

  const stop = useCallback(() => {
    closeMic();
    setMode("off");
    setPhase("idle");
  }, []);

  const interrupt = useCallback(() => mic.current?.hush(), []);
  const level = useCallback(() => mic.current?.level() ?? 0, []);

  // The shopper's pick of voice, kept in this browser. Picking one plays a short hello in it.
  const [voice, setVoiceState] = useState<string | null>(null);
  const voiceRef = useRef<string | null>(null);
  useEffect(() => {
    try {
      voiceRef.current = localStorage.getItem("niche-voice");
      setVoiceState(voiceRef.current);
    } catch {
      // storage blocked: the server's default voice
    }
  }, []);
  const setVoice = useCallback(
    (key: string, name: string) => {
      voiceRef.current = key;
      setVoiceState(key);
      try {
        localStorage.setItem("niche-voice", key);
      } catch {
        // storage blocked: this visit only
      }
      const hello = pick([`Hey, it's ${name}! Better?`, `Hi, ${name} here. How's this?`, `It's ${name} now. Sound good?`]);
      if (modeRef.current === "voice" && mic.current) {
        mic.current.hush();
        speak(hello);
      } else {
        // Not in a conversation: play the sample straight away (this runs from the click that picked it).
        api.speak(hello, key).then((bytes) => new Audio(URL.createObjectURL(new Blob([bytes], { type: "audio/mpeg" }))).play(), () => {});
      }
    },
    [speak],
  );

  const register = useCallback((skill: Skill) => {
    skillsRef.current = [...skillsRef.current.filter((s) => s.id !== skill.id), skill];
    setSkills(skillsRef.current);
    return () => {
      skillsRef.current = skillsRef.current.filter((s) => s !== skill);
      setSkills(skillsRef.current);
    };
  }, []);

  const previousPath = useRef(pathname);
  useEffect(() => {
    if (previousPath.current === "/shop" && pathname !== "/shop") stop();
    previousPath.current = pathname;
  }, [pathname, stop]);

  // A tip belongs to the page it was shown on: clear it on navigation (the next page may show its own below).
  useEffect(() => {
    setNudge(null);
  }, [pathname]);

  // Arriving on a page mid-conversation: it says what it can help with here. With the conversation closed, the
  // page's opener waits by the dock instead.
  const current = skills.at(-1) ?? null;
  useEffect(() => {
    if (modeRef.current === "off") {
      if (current?.intro && !introduced.current.has(current.id)) setNudge(current.intro);
      return;
    }
    // Only pages with something of their own to offer speak up; the shopping chat carries on as it was.
    if (current && !busy.current) introduce(current);
  }, [current, introduce]);

  useEffect(() => () => closeMic(), []);

  const shopState: ShopState = useMemo(
    () => ({
      profileId,
      searchId,
      fresh: !!freshId && freshId === searchId,
      budget,
      keepToBudget,
      setKeepToBudget(on) {
        setKeep(on);
        try {
          localStorage.setItem("keep-to-budget", on ? "1" : "0");
        } catch {
          // storage blocked: applies to this visit only
        }
      },
      refreshBudget() {
        if (profileRef.current) api.budget(profileRef.current).then(setBudget, () => setBudget(null));
      },
      async accept(proposal) {
        const id = profileRef.current;
        if (!id || !proposal.proposed || busy.current) return;
        setError(null);
        const price = proposal.proposed_price ? ` under $${Math.round(proposal.proposed_price)}` : "";
        const size = proposal.proposed_size ? ` in size ${proposal.proposed_size}` : "";
        const before = turnsRef.current;
        const line = `Searching for ${proposal.proposed}${size}${price}.`;
        commit([
          ...before,
          { role: "user", text: "Yes, search for that", skill: "shop" },
          { role: "agent", text: line, brief: proposal.proposed, skill: "shop" },
        ]);
        try {
          const { search_id } = await api.search(id, proposal.proposed, {
            maxItemPrice: proposal.proposed_price,
            size: proposal.proposed_size,
            mustHave: proposal.proposed_must_have,
            category: proposal.proposed_category,
            brands: proposal.proposed_brands,
          });
          setSearch(search_id, true);
          commit(turnsRef.current);
          if (pathRef.current !== "/shop") router.push("/shop");
          speak("On it, searching now.");
        } catch (err) {
          setError((err as Error).message);
          commit(before);
        }
      },
      reset() {
        setSearch(null);
        commit(turnsRef.current.filter((t) => t.skill !== "shop"));
      },
      announce(id, text) {
        if (id !== freshId) return;
        setFreshId(null);
        add({ role: "agent", text, skill: "shop", done: true });
        if (modeRef.current === "voice") speak(text);
        else if (modeRef.current === "off") setNudge(text);
      },
    }),
    [profileId, searchId, freshId, budget, keepToBudget, commit, add, setSearch, router, speak],
  );

  const assistant: Assistant = {
    turns,
    mode,
    phase,
    error,
    nudge,
    voice,
    setVoice,
    dismissNudge: () => setNudge(null),
    skill: current ?? SHOP_SKILL,
    start,
    stop,
    send,
    say,
    phrase,
    interrupt,
    level,
    register,
    shop: shopState,
  };

  return <AssistantContext.Provider value={assistant}>{children}</AssistantContext.Provider>;
}

type View = "recent" | "all" | "hidden";
type Placement = "bottom" | "hero" | "side";

/** The assistant's home on every page: a small bar at the bottom that opens into the conversation. On Shop it starts
 * in the middle of the page ("what are you shopping for?"), then moves to a sidebar beside the results. */
export function AssistantDock() {
  const a = useAssistant();
  const pathname = usePathname();
  // "recent" keeps only the latest exchange on screen so the page stays visible; "all" shows the whole history.
  const [view, setView] = useState<View>("recent");
  const [draft, setDraft] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const { start, mode } = a;
  const placement: Placement =
    pathname === "/shop" && a.shop.profileId ? (a.shop.searchId ? "side" : "hero") : "bottom";

  // Dock the results conversation directly below the site navigation, including when it wraps.
  useEffect(() => {
    if (placement !== "side") return;
    const header = document.querySelector("body header");
    if (!header) return;
    const measure = () => document.documentElement.style.setProperty("--site-header-height", `${header.getBoundingClientRect().height}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    return () => {
      observer.disconnect();
      document.documentElement.style.removeProperty("--site-header-height");
    };
  }, [placement]);

  // Space twice (outside a text field) opens the conversation to type.
  useEffect(() => {
    const tapped = doubleSpace();
    const onKey = (e: KeyboardEvent) => {
      if (!tapped(e)) return;
      e.preventDefault();
      setView((v) => (v === "hidden" ? "recent" : v));
      if (mode !== "text") start("text");
      requestAnimationFrame(() => input.current?.focus());
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode, start]);

  useEffect(() => {
    if (mode === "text") input.current?.focus();
  }, [mode]);

  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollIntoView, which React rejects as a cleanup.
    end.current?.scrollIntoView({ block: "end" });
  }, [a.turns, a.phase, view, placement]);

  function submit() {
    if (!draft.trim()) return;
    if (mode === "off") start("text");
    a.send(draft);
    setDraft("");
  }

  const shopping = pathname === "/shop" && a.skill.id === "shop";
  const visibleTurns = a.turns.filter((turn) => pathname === "/shop" ? turn.skill === "shop" : turn.skill !== "shop");
  const shopTurns = a.turns.filter((t) => t.skill === "shop");
  const last = visibleTurns.at(-1);
  const pending = outstandingProposal(shopTurns);
  const idle = a.phase === "idle" || a.phase === "listening";
  const suggestions =
    !shopping || !idle || !a.shop.profileId || placement === "hero"
      ? []
      : shopTurns.length === 0
        ? STARTERS
        : last?.done
          ? FOLLOW_UPS
          : [];
  const everything = placement === "side" || view === "all";
  const lastAsk = visibleTurns.findLastIndex((t) => t.role === "user");
  const shown = everything ? visibleTurns : visibleTurns.slice(lastAsk < 0 ? -2 : lastAsk).slice(-4);
  const earlier = visibleTurns.length - shown.length;

  const transcript = (
    <div className="overflow-y-auto px-4 pt-3 pb-2 grid gap-3 content-start min-h-0 flex-1">
      {earlier > 0 && (
        <button type="button" onClick={() => setView("all")} className="label underline justify-self-center">
          Show {earlier} earlier
        </button>
      )}
      {shown.map((t, i) => (
        <Line key={earlier + i} turn={t} pending={t === pending && idle} onAccept={a.shop.accept} />
      ))}
      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {suggestions.map((text) => (
            <button key={text} onClick={() => a.send(text)} className="label border border-ink px-3 py-1.5 text-left">
              {text}
            </button>
          ))}
        </div>
      )}
      {a.error && <p className="text-sm" role="alert">{a.error}</p>}
      <div ref={end} />
    </div>
  );

  const textBox = (
    <form
      className="flex items-end gap-2 flex-1 min-w-0"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <textarea
        ref={input}
        rows={1}
        className="flex-1 min-w-0 resize-none bg-transparent outline-none text-sm py-1.5 placeholder:text-muted"
        placeholder={a.phase === "thinking" ? "Niche is thinking\u2026" : a.skill.placeholder ?? "Ask Niche anything"}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
          if (e.key === "Escape") a.stop();
        }}
      />
      <button disabled={!draft.trim() || a.phase === "thinking"} className="label underline disabled:no-underline disabled:text-muted py-1.5">
        Send
      </button>
    </form>
  );

  const voiceBar = (
    <>
      <button
        type="button"
        onClick={a.phase === "speaking" ? a.interrupt : undefined}
        aria-label={a.phase === "speaking" ? "Cut in" : "Listening"}
        className="shrink-0"
      >
        <Orb phase={a.phase} level={a.level} />
      </button>
      <div className="min-w-0 flex-1">
        <p className="text-sm" role="status" aria-live="polite">
          {STATUS[a.phase]}
        </p>
        <p className="label text-muted truncate">{a.skill.label}</p>
      </div>
    </>
  );

  // Shop, before the first search: the assistant is the page. Say it or type it, right in the middle.
  if (placement === "hero") {
    return (
      <div className="fixed inset-x-0 top-[22vh] z-[800] flex justify-center px-4 pointer-events-none">
        <section
          aria-label="Niche assistant"
          className="pointer-events-auto w-full max-w-2xl border border-ink bg-paper shadow-[0_10px_32px_rgba(0,0,0,.16)] grid"
        >
          <div className="px-5 pt-5 pb-3 grid gap-2">
            <div className="flex items-baseline justify-between">
              <p className="label">Niche</p>
              <VoicePicker />
            </div>
            <h2 className="text-display">What are you shopping for?</h2>
            <p className="text-sm text-muted">
              Say it out loud or type it, like you would to a friend. Niche searches big stores, small shops and secondhand
              for you, then you can keep talking to refine it.
            </p>
          </div>
          {visibleTurns.length > 0 && <div className="max-h-[28vh] flex flex-col rule-t">{transcript}</div>}
          <div className="rule-t flex items-center gap-3 px-4 py-3">
            {mode === "voice" ? (
              <>
                {voiceBar}
                <button type="button" onClick={() => start("text")} className="label underline">Type</button>
              </>
            ) : (
              <>
                {mode === "off" && (
                  <button type="button" onClick={() => start("voice")} className="flex items-center gap-2 label bg-ink text-paper pl-2 pr-3 py-1.5 shrink-0">
                    <span className="w-3 h-3 rounded-full bg-paper" /> Talk
                  </button>
                )}
                {mode === "text" && (
                  <button type="button" onClick={() => start("voice")} className="label underline shrink-0">Talk</button>
                )}
                {textBox}
              </>
            )}
            {mode !== "off" && (
              <button type="button" onClick={a.stop} className="text-xl leading-none px-1" aria-label="End conversation">×</button>
            )}
          </div>
          <div className="rule-t flex flex-wrap gap-2 px-4 py-3">
            {STARTERS.map((text) => (
              <button key={text} onClick={() => a.send(text)} className="label border border-ink px-3 py-1.5 text-left">
                {text}
              </button>
            ))}
          </div>
        </section>
      </div>
    );
  }

  // Shop, with results: a sidebar on the right (bottom sheet on phones), conversation always in view.
  if (placement === "side") {
    return (
      <section
        aria-label="Niche assistant"
        className="assistant-sidebar fixed z-[800] inset-x-0 bottom-0 max-h-[45dvh] lg:left-auto lg:right-0 lg:top-[var(--site-header-height,56px)] lg:bottom-0 lg:max-h-none lg:w-[320px] border-t lg:border-t-0 lg:border-l border-ink bg-paper flex flex-col"
      >
        <div className="rule-b flex items-baseline justify-between px-4 py-2">
          <span className="text-sm font-medium">
            Niche <VoicePicker down />
          </span>
          <button type="button" onClick={a.shop.reset} className="label underline">New search</button>
        </div>
        {transcript}
        <div className="rule-t flex items-center gap-3 px-3 py-2">
          {mode === "voice" ? (
            <>
              {voiceBar}
              <button type="button" onClick={() => start("text")} className="label underline">Type</button>
            </>
          ) : (
            <>
              <button type="button" onClick={() => start("voice")} className="label underline shrink-0">Talk</button>
              {textBox}
            </>
          )}
          {mode !== "off" && (
            <button type="button" onClick={a.stop} className="text-xl leading-none px-1" aria-label="End conversation">×</button>
          )}
        </div>
      </section>
    );
  }

  if (mode === "off") {
    return (
      <div className="fixed inset-x-0 bottom-0 z-[900] flex flex-col items-center gap-2 px-4 pb-4 pointer-events-none">
        {a.nudge && (
          <div className="pointer-events-auto relative max-w-md">
            <button
              type="button"
              onClick={() => start("voice")}
              className="w-full border border-ink bg-paper py-3 pl-4 pr-9 text-left text-sm shadow-[0_6px_18px_rgba(0,0,0,.14)]"
            >
              <span className="label block mb-1">Niche</span>
              {a.nudge}
            </button>
            {/* Close it to get the page back; the "Talk to Niche" bar stays. */}
            <button
              type="button"
              onClick={a.dismissNudge}
              aria-label="Close"
              className="absolute right-1.5 top-1.5 size-6 grid place-items-center text-base leading-none hover:bg-plinth"
            >
              ×
            </button>
          </div>
        )}
        <div className="pointer-events-auto flex items-stretch border border-ink bg-paper shadow-[0_6px_18px_rgba(0,0,0,.14)]">
          <button type="button" onClick={() => start("voice")} className="flex items-center gap-3 pl-3 pr-4 py-2">
            <Orb phase="idle" level={() => 0} />
            <span className="text-display leading-none">Talk to Niche</span>
          </button>
          <button type="button" onClick={() => start("text")} className="label border-l border-ink px-3" title="Or press space twice">
            Type
          </button>
          <span className="border-l border-ink px-3 grid place-items-center">
            <VoicePicker />
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-x-0 bottom-0 z-[900] flex justify-center px-3 pb-3 pointer-events-none">
      <section
        aria-label="Niche assistant"
        className={`pointer-events-auto w-full max-w-2xl border border-ink bg-paper shadow-[0_8px_28px_rgba(0,0,0,.18)] flex flex-col ${
          view === "all" ? "max-h-[60dvh]" : "max-h-[34dvh]"
        }`}
      >
        {view !== "hidden" && (visibleTurns.length > 0 || a.error || suggestions.length > 0) && <div className="rule-b flex flex-col min-h-0">{transcript}</div>}
        <div className="flex items-center gap-3 px-3 py-2">
          {mode === "voice" ? voiceBar : textBox}
          <div className="flex items-center gap-3 shrink-0">
            <VoicePicker />
            <button type="button" onClick={() => start(mode === "voice" ? "text" : "voice")} className="label underline py-1.5">
              {mode === "voice" ? "Type" : "Talk"}
            </button>
            {view !== "hidden" && (
              <button type="button" onClick={() => setView(view === "all" ? "recent" : "all")} className="label underline py-1.5">
                {view === "all" ? "Less" : "History"}
              </button>
            )}
            <button type="button" onClick={() => setView(view === "hidden" ? "recent" : "hidden")} className="label underline py-1.5" aria-expanded={view !== "hidden"}>
              {view === "hidden" ? "Show" : "Hide"}
            </button>
            <button type="button" onClick={a.stop} className="text-xl leading-none px-1" aria-label="End conversation">
              ×
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}

const STATUS: Record<Phase, string> = {
  idle: "Ready",
  listening: "Listening — just talk",
  hearing: "Hearing you…",
  thinking: "Thinking…",
  speaking: "Speaking · tap the circle to cut in",
};

const VOICES = ["Sierra", "Michelle", "Jacqueline", "Corey", "Cooper", "Ronald"].map((name) => ({ key: name.toLowerCase(), name }));

/** Who Niche sounds like. Picking a voice plays a short hello in it. */
function VoicePicker({ down = false }: { down?: boolean }) {
  const { voice, setVoice } = useAssistant();
  const [open, setOpen] = useState(false);
  const [voices, setVoices] = useState(VOICES);
  useEffect(() => {
    api.voices().then(setVoices, () => {});
  }, []);
  const current = voices.find((v) => v.key === voice) ?? voices[0];
  return (
    <span className="relative inline-block">
      <button type="button" onClick={() => setOpen((o) => !o)} className="label underline py-1.5" aria-expanded={open} aria-haspopup="listbox">
        Voice: {current?.name}
      </button>
      {open && (
        <ul
          role="listbox"
          aria-label="Niche's voice"
          className={`absolute ${down ? "left-0 top-full mt-2" : "right-0 bottom-full mb-2"} z-10 w-40 border border-ink bg-paper shadow-[0_6px_18px_rgba(0,0,0,.14)] py-1`}
        >
          {voices.map((v) => (
            <li key={v.key}>
              <button
                type="button"
                role="option"
                aria-selected={v.key === current?.key}
                onClick={() => {
                  setVoice(v.key, v.name);
                  setOpen(false);
                }}
                className={`w-full text-left text-sm px-3 py-1.5 hover:bg-plinth ${v.key === current?.key ? "font-medium" : ""}`}
              >
                {v.key === current?.key ? "\u2713 " : ""}
                {v.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}

/** A black circle that swells with the mic level while listening and breathes while the assistant talks. */
function Orb({ phase, level }: { phase: Phase; level: () => number }) {
  const ring = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    let frame = 0;
    const tick = () => {
      const listening = phase === "listening" || phase === "hearing";
      if (ring.current) ring.current.style.transform = `scale(${1 + (listening ? level() * 0.9 : 0)})`;
      frame = requestAnimationFrame(tick);
    };
    tick();
    return () => cancelAnimationFrame(frame);
  }, [phase, level]);
  return (
    <span className="relative grid place-items-center w-9 h-9">
      <span ref={ring} className="absolute inset-0 rounded-full border border-ink transition-transform duration-75" />
      <span
        className={`w-5 h-5 rounded-full bg-ink ${phase === "speaking" ? "animate-pulse" : ""} ${
          phase === "thinking" ? "animate-spin rounded-none w-3 h-3" : ""
        }`}
      />
    </span>
  );
}

function Line({ turn, pending, onAccept }: { turn: Turn; pending: boolean; onAccept: (t: ChatTurn) => void }) {
  if (turn.role === "user") {
    return <p className="justify-self-end max-w-[85%] bg-plinth px-3 py-2 text-sm">{turn.text}</p>;
  }
  return (
    <div className="justify-self-start max-w-[85%]">
      <p className="label mb-1">Niche</p>
      <div className="border border-ink px-3 py-2">
        {turn.linked?.map((page) => (
          <p key={page.url} className="label text-muted mb-1">
            {page.readable ? `Read: ${page.title ?? page.site}` : `Couldn't open ${page.site ?? "that link"}`}
          </p>
        ))}
        <p className="text-sm">{turn.text}</p>
        {turn.recalled?.length ? (
          <p className="label text-muted mt-2">From your earlier finds</p>
        ) : null}
        {turn.recalled?.length ? (
          <ul className="mt-1 grid gap-1">
            {turn.recalled.map((f) => (
              <li key={f.url} className="text-xs">
                <a href={f.url} target="_blank" rel="noopener noreferrer" className="underline">
                  {f.title}
                </a>
                <span className="text-muted">
                  {[f.store, f.price != null ? `${f.price} ${f.currency ?? ""}`.trim() : null].filter(Boolean).map((x) => ` · ${x}`)}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
        {turn.brief && <p className="label text-muted mt-1">Searched: {turn.brief}</p>}
        {pending && (
          <div className="flex gap-3 mt-2">
            <button onClick={() => onAccept(turn)} className="label bg-ink text-paper px-3 py-1.5">
              Yes, search
            </button>
            <span className="label text-muted self-center">or say what to change</span>
          </div>
        )}
      </div>
    </div>
  );
}

/** The latest search the agent offered that hasn't been run yet, matching the backend's rule. */
function outstandingProposal(turns: ChatTurn[]) {
  for (let i = turns.length - 1; i >= 0; i--) {
    const m = turns[i];
    if (m.role !== "agent") continue;
    if (m.brief) return null;
    if (m.proposed) return m;
  }
  return null;
}
