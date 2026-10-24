"use client";

// Ask Niche from anywhere: press space twice (outside a text field) or tap the corner button.
// On the shop page that jumps to the chat's own box; elsewhere it opens a small box that sends to the same chat.

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { VoiceButton } from "@/components/voice";
import { askNiche, askUrl, doubleSpace } from "@/lib/assistant";

export function AssistantLauncher() {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const input = useRef<HTMLTextAreaElement>(null);
  const router = useRouter();
  const pathname = usePathname();
  const onShop = pathname === "/shop";

  useEffect(() => {
    const tapped = doubleSpace();
    const onKey = (e: KeyboardEvent) => {
      if (!tapped(e)) return;
      e.preventDefault();
      // The shop chat is the assistant: focus it rather than stacking a second box on top.
      const chat = document.querySelector<HTMLTextAreaElement>("[data-ask-niche]");
      if (chat && !chat.disabled) {
        chat.scrollIntoView({ block: "nearest" });
        chat.focus();
      } else setOpen(true);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Typed and spoken messages take the same path into the chat.
  function ask(text: string) {
    const message = text.trim();
    if (!message) return;
    setDraft("");
    setOpen(false);
    if (!askNiche(message)) router.push(askUrl(message));
  }

  if (!open) {
    if (onShop) return null;
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-4 right-4 z-[900] label border border-ink bg-paper px-3 py-2 shadow-[0_4px_12px_rgba(0,0,0,.12)]"
        title="Or press space twice"
      >
        Ask Niche <span className="text-muted hidden sm:inline">· space space</span>
      </button>
    );
  }

  return (
    <div className="fixed inset-0 z-[1000] flex items-end sm:items-start justify-center sm:pt-[18vh]" role="dialog" aria-modal aria-label="Ask Niche">
      <button aria-label="Close" className="absolute inset-0 cursor-default bg-ink/10" onClick={() => setOpen(false)} />
      <form
        className="relative w-full sm:max-w-lg mx-4 mb-4 sm:mb-0 border border-ink bg-paper shadow-[0_8px_24px_rgba(0,0,0,.18)]"
        onSubmit={(e) => {
          e.preventDefault();
          ask(draft);
        }}
      >
        <div className="rule-b flex items-baseline justify-between px-3 py-2">
          <span className="text-display">Ask Niche</span>
          <button type="button" onClick={() => setOpen(false)} className="text-xl leading-none" aria-label="Close">
            ×
          </button>
        </div>
        <div className="flex items-end gap-2 px-3 py-2">
          <textarea
            ref={input}
            rows={2}
            className="flex-1 resize-none bg-transparent outline-none text-sm placeholder:text-muted"
            placeholder="Find me a vintage leather jacket under $150"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                ask(draft);
              }
            }}
          />
          <div className="grid gap-1 justify-items-end">
            <VoiceButton context="shop" label="Talk" onTranscript={ask} />
            <button disabled={!draft.trim()} className="label underline disabled:no-underline disabled:text-muted">
              Send
            </button>
          </div>
        </div>
        <p className="label text-muted px-3 pb-2">Enter to send · Esc to close</p>
      </form>
    </div>
  );
}
