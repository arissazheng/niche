"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { SectionTitle } from "@/components/chrome";
import { Drawer } from "@/components/drawer";
import { api } from "@/lib/api";
import { setFriendView } from "@/lib/session";
import { TIER_LABELS, type ChatTurn, type Listing, type SearchJob } from "@/lib/types";

// Shopping for a friend through the moodboard link they shared: the agent uses their taste and sizes, you set the
// price. No budget strip, no "mark as bought": the friend's bank and history are untouched.

const DONE = new Set(["completed", "partial", "failed", "interrupted"]);
const STARTERS = ["A birthday gift under $40", "Something for a night out", "A cosy knit under $60"];
const FOLLOW_UPS = ["Compare #1 and #2", "Which would they love most?", "Something cheaper"];

export default function GiftPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [name, setName] = useState<string | null>(null);
  const [gone, setGone] = useState(false);
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<{ id: string; url: string } | null>(null);
  const [job, setJob] = useState<SearchJob | null>(null);
  const [selected, setSelected] = useState<Listing | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.shared(token).then(
      (view) => {
        setName(view.profile.onboarding.name || "your friend");
        setFriendView({ token, name: view.profile.onboarding.name.trim() });
      },
      () => setGone(true),
    );
  }, [token]);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, thinking]);

  // Results stream in while the search runs.
  useEffect(() => {
    if (!search) return;
    let stop = false;
    const poll = async () => {
      const next = await api.getSearch(search.url).catch(() => null);
      if (stop || !next) return;
      setJob(next);
      if (!DONE.has(next.status)) setTimeout(poll, 2000);
    };
    poll();
    return () => {
      stop = true;
    };
  }, [search]);

  async function send(text: string) {
    if (!text.trim() || thinking) return;
    const next: ChatTurn[] = [...messages, { role: "user", text: text.trim() }];
    setMessages(next);
    setDraft("");
    setThinking(true);
    setError(null);
    try {
      const reply = await api.giftChat(token, next, search?.id);
      const turn: ChatTurn = { role: "agent", text: reply.reply };
      if (reply.action === "search") turn.brief = reply.brief;
      if (reply.action === "propose") turn.proposed = reply.brief;
      setMessages([...next, turn]);
      if (reply.search_id && reply.status_url) {
        setJob(null);
        setSearch({ id: reply.search_id, url: reply.status_url });
      }
    } catch (err) {
      setError((err as Error).message);
      setMessages(messages);
    } finally {
      setThinking(false);
    }
  }

  if (gone) {
    return (
      <p className="px-4 mt-10 text-display">
        This link was turned off. Ask your friend to share their moodboard again.
      </p>
    );
  }
  if (!name) return <p className="px-4 mt-10 label">Loading…</p>;

  const results = job?.results ?? [];
  const finished = !!job && DONE.has(job.status);
  const last = messages.at(-1);
  const suggestions = thinking
    ? []
    : messages.length === 0
      ? STARTERS
      : finished && results.length > 1 && last?.role === "agent" && last.brief
        ? FOLLOW_UPS
        : [];

  return (
    <div className="px-4 mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] items-start">
      <section className="order-2 lg:order-1 min-w-0">
        <SectionTitle aside={<Link href={`/taste?board=${token}`} className="underline">Their moodboard</Link>}>
          {search ? (finished ? `${results.length} gift ideas` : "Finding gift ideas") : `A gift for ${name}`}
        </SectionTitle>
        {!search && (
          <p className="text-sm max-w-md">
            Tell Niche what you have in mind. It searches with {name}&apos;s taste and sizes, and you set the price.
          </p>
        )}
        {search && !finished && (
          <p className="label mb-3 animate-pulse">
            {results.length ? "Ranking by their taste…" : "Searching stores, small labels and secondhand…"}
          </p>
        )}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          {results.map((item, i) => (
            <button key={item.id} onClick={() => setSelected(item)} className="text-left">
              <div className="bg-plinth aspect-[3/4] flex items-center justify-center overflow-hidden">
                {item.image_urls[0] && (
                  // eslint-disable-next-line @next/next/no-img-element -- marketplace photos
                  <img src={item.image_urls[0]} alt="" className="h-full w-full object-contain" />
                )}
              </div>
              <div className="flex items-start justify-between mt-1 gap-2">
                <span className="text-display">{i + 1}</span>
                <span className="label pt-1 text-right">{storeLabel(item)}</span>
              </div>
              <p className="text-sm">{item.title}</p>
              <p className="text-sm">{item.price.toFixed(2)} {item.currency}</p>
            </button>
          ))}
        </div>
      </section>

      <aside className="order-1 lg:order-2 flex flex-col border border-ink bg-paper h-[60dvh] lg:h-[calc(100dvh-8rem)] lg:sticky lg:top-4">
        <div className="rule-b px-3 py-2">
          <span className="text-display">Shopping for {name}</span>
        </div>
        <div className="flex-1 overflow-y-auto px-3 py-3 grid gap-3 content-start">
          {messages.length === 0 && (
            <p className="text-sm text-muted">What&apos;s the occasion? Describe a gift like you would to a friend.</p>
          )}
          {messages.map((m, i) =>
            m.role === "user" ? (
              <p key={i} className="justify-self-end max-w-[85%] bg-plinth px-3 py-2 text-sm">{m.text}</p>
            ) : (
              <div key={i} className="justify-self-start max-w-[85%]">
                <p className="label mb-1">Niche</p>
                <div className="border border-ink px-3 py-2">
                  <p className="text-sm">{m.text}</p>
                  {m.brief && <p className="label text-muted mt-1">Searched: {m.brief}</p>}
                  {m.proposed && m === last && !thinking && (
                    <button onClick={() => send("Yes, search for that")} className="label bg-ink text-paper px-3 py-1.5 mt-2">
                      Yes, search
                    </button>
                  )}
                </div>
              </div>
            ),
          )}
          {suggestions.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {suggestions.map((text) => (
                <button key={text} onClick={() => send(text)} className="label border border-ink px-3 py-1.5 text-left">
                  {text}
                </button>
              ))}
            </div>
          )}
          {thinking && <p className="label animate-pulse">Niche is thinking…</p>}
          {error && <p className="text-sm">{error}</p>}
          <div ref={end} />
        </div>
        <form
          className="rule-t flex items-end gap-2 px-3 py-2"
          onSubmit={(e) => {
            e.preventDefault();
            send(draft);
          }}
        >
          <textarea
            rows={2}
            className="flex-1 resize-none bg-transparent outline-none text-sm placeholder:text-muted"
            placeholder={`Something ${name} would wear to a gallery opening…`}
            value={draft}
            disabled={thinking}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(draft);
              }
            }}
          />
          <button disabled={thinking || !draft.trim()} className="label underline disabled:no-underline disabled:text-muted">
            Send
          </button>
        </form>
      </aside>

      <Drawer open={!!selected} onClose={() => setSelected(null)}>
        {selected && (
          <div className="grid gap-4">
            <div>
              <p className="text-display">{selected.title}</p>
              <p className="text-display">{storeLabel(selected)}</p>
              <p className="text-sm mt-1">{selected.price.toFixed(2)} {selected.currency}</p>
            </div>
            {!!selected.risks?.length && (
              <div role="alert" className="border-2 border-ink p-3 grid gap-1">
                <span className="label">⚠ Before you buy</span>
                {selected.risks.map((risk) => (
                  <p key={risk} className="text-sm">{risk}</p>
                ))}
              </div>
            )}
            <div className="grid gap-1">
              <span className="label">Why {name} would like it</span>
              <p className="text-sm">{selected.reason}</p>
              {[...new Set(selected.warnings)].map((w) => (
                <p key={w} className="text-xs text-muted">— {w}</p>
              ))}
            </div>
            <a href={selected.url} target="_blank" rel="noopener noreferrer" className="label bg-ink text-paper px-4 py-2 justify-self-start">
              View on {selected.retailer ?? selected.seller ?? selected.source} ↗
            </a>
          </div>
        )}
      </Drawer>
    </div>
  );
}

function storeLabel(listing: Listing) {
  if (!listing.retailer) return listing.seller ?? listing.source;
  return listing.tier ? `${listing.retailer} · ${TIER_LABELS[listing.tier]}` : listing.retailer;
}
