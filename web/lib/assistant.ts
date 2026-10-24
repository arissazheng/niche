// One path into the shop assistant ("Ask Niche") for typed and spoken messages, from any page.
// The shop page claims messages while it is open; anywhere else the caller sends the shopper to /shop?ask=…

const ASK = "niche:ask";
export const ASK_PARAM = "ask";

/** Hands text to the Ask Niche chat on this page. False when there is none, so the caller can open /shop. */
export function askNiche(text: string): boolean {
  const event = new CustomEvent<string>(ASK, { detail: text, cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

export const askUrl = (text: string) => `/shop?${ASK_PARAM}=${encodeURIComponent(text)}`;

/** The chat registers here to receive messages typed or spoken elsewhere on the page. */
export function onAsk(handler: (text: string) => void) {
  const listener = (e: Event) => {
    e.preventDefault();
    handler((e as CustomEvent<string>).detail);
  };
  window.addEventListener(ASK, listener);
  return () => window.removeEventListener(ASK, listener);
}

/** Reads and clears a message carried in the URL, so a reload doesn't send it twice. */
export function takeAskFromUrl(): string | null {
  const url = new URL(window.location.href);
  const text = url.searchParams.get(ASK_PARAM)?.trim();
  if (!text) return null;
  url.searchParams.delete(ASK_PARAM);
  window.history.replaceState(window.history.state, "", url);
  return text;
}

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
