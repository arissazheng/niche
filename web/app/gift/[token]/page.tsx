"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import { SectionTitle } from "@/components/chrome";
import { Drawer } from "@/components/drawer";
import { MarketCheck } from "@/components/market-check";
import { api } from "@/lib/api";
import { useAssistant, useAssistantSkill } from "@/lib/assistant";
import { setFriendView } from "@/lib/session";
import { TIER_LABELS, type ChatTurn, type Listing, type SearchJob } from "@/lib/types";

// Shopping for a friend through the moodboard link they shared: the agent uses their taste and sizes, you set the
// price. No budget strip, no "mark as bought": the friend's bank and history are untouched.

const DONE = new Set(["completed", "partial", "failed", "interrupted"]);
const STARTERS = ["A birthday gift under $40", "Something for a night out", "A cosy knit under $60"];

export default function GiftPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const [name, setName] = useState<string | null>(null);
  const [gone, setGone] = useState(false);
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState<{ id: string; url: string } | null>(null);
  const [job, setJob] = useState<SearchJob | null>(null);
  const [selected, setSelected] = useState<Listing | null>(null);
  const latest = useRef(messages);
  latest.current = messages;
  const assistant = useAssistant();
  const { say } = assistant;

  useEffect(() => {
    api.shared(token).then(
      (view) => {
        setName(view.profile.onboarding.name || "your friend");
        setFriendView({ token, name: view.profile.onboarding.name.trim() });
      },
      () => setGone(true),
    );
  }, [token]);

  // The assistant does the talking here too, with the friend's taste instead of the shopper's own.
  useAssistantSkill(
    name
      ? {
          id: "gift",
          label: `Finding a gift for ${name}`,
          intro: `Let's find something ${name} will love! What do you have in mind, and what's your budget?`,
          placeholder: "A birthday gift under $40",
          handle: send,
        }
      : null,
  );

  // Results stream in while the search runs.
  useEffect(() => {
    if (!search) return;
    let stop = false;
    const poll = async () => {
      const next = await api.getSearch(search.url).catch(() => null);
      if (stop || !next) return;
      setJob(next);
      if (!DONE.has(next.status)) setTimeout(poll, 2000);
      else {
        const n = next.results?.length ?? 0;
        say(n ? `Found ${n} ideas! Number 1 is ${next.results![0].title}. Want me to compare a few?` : "Nothing came back for that one. Want to try it another way?");
      }
    };
    poll();
    return () => {
      stop = true;
    };
  }, [search, say]);

  /** One turn of the gift conversation; resolves to what the assistant says back. */
  async function send(text: string): Promise<string> {
    const next: ChatTurn[] = [...latest.current, { role: "user", text: text.trim() }];
    latest.current = next;
    setMessages(next);
    setError(null);
    try {
      const reply = await api.giftChat(token, next, search?.id);
      const turn: ChatTurn = { role: "agent", text: reply.reply };
      if (reply.action === "search") turn.brief = reply.brief;
      if (reply.action === "propose") turn.proposed = reply.brief;
      latest.current = [...next, turn];
      setMessages(latest.current);
      if (reply.search_id && reply.status_url) {
        setJob(null);
        setSearch({ id: reply.search_id, url: reply.status_url });
      }
      return reply.reply;
    } catch (err) {
      latest.current = latest.current.slice(0, -1);
      setMessages(latest.current);
      setError((err as Error).message);
      throw err;
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
  return (
    <div className="px-4 mt-6">
      <section className="min-w-0">
        <SectionTitle aside={<Link href={`/taste?board=${token}`} className="underline">Their moodboard</Link>}>
          {search ? (finished ? `${results.length} gift ideas` : "Finding gift ideas") : `A gift for ${name}`}
        </SectionTitle>
        {!search && (
          <div className="grid gap-4 justify-items-start">
            <p className="text-sm max-w-md">
              Tell Niche what you have in mind, out loud or typed at the bottom of the page. It searches with {name}&apos;s
              taste and sizes, and you set the price.
            </p>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => assistant.start("voice")} className="label bg-ink text-paper px-3 py-1.5">
                Talk to Niche
              </button>
              {STARTERS.map((text) => (
                <button key={text} onClick={() => assistant.send(text)} className="label border border-ink px-3 py-1.5 text-left">
                  {text}
                </button>
              ))}
            </div>
          </div>
        )}
        {error && <p className="text-sm mt-2">{error}</p>}
        {search && !finished && (
          <p className="label mb-3 animate-pulse">
            {results.length ? "Ranking by their taste…" : "Searching stores, small labels and secondhand…"}
          </p>
        )}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
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
            {search && <MarketCheck searchId={search.id} listingId={selected.id} />}
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
