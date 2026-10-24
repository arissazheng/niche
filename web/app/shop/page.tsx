"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useSpacetimeDB, useTable } from "spacetimedb/react";
import { Checkout } from "@/components/checkout";
import { SectionTitle } from "@/components/chrome";
import { Drawer } from "@/components/drawer";
import { VoiceButton } from "@/components/voice";
import { api } from "@/lib/api";
import { getProfileId } from "@/lib/session";
import { tables } from "@/lib/spacetime";
import { TIER_LABELS, type Budget, type ChatTurn, type Listing, type SearchJob } from "@/lib/types";

const DONE = new Set(["completed", "partial", "failed", "interrupted"]);
const EXAMPLES = ["an asymmetrical buttoned top", "black knee-high boots under $120", "a vintage leather jacket"];

interface Thread {
  messages: ChatTurn[];
  searchId: string | null;
}

// The conversation is a per-browser convenience; searches themselves live on the server.
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

export default function ShopPage() {
  const [profileId, setProfileIdState] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [thinking, setThinking] = useState(false);
  const [job, setJob] = useState<SearchJob | null>(null);
  const [selected, setSelected] = useState<Listing | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  const pollToken = useRef(0);

  // The shopper's mock bank (Capital One Nessie): shown above the chat, and read by the agent every turn.
  function refreshBudget(id = profileId) {
    if (id) api.budget(id).then(setBudget, () => setBudget(null));
  }

  // Listings stream in from SpacetimeDB as each marketplace returns; ranking then reorders them in place.
  const { isActive } = useSpacetimeDB();
  const [liveRows] = useTable(tables.listing.where((r) => r.searchId.eq(searchId ?? "")), { enabled: !!searchId });
  const [liveSearch] = useTable(tables.search.where((r) => r.searchId.eq(searchId ?? "")), { enabled: !!searchId });
  const liveListings: Listing[] = [...liveRows]
    .sort((a, b) => (a.rank ?? 1e9) - (b.rank ?? 1e9))
    .map((r) => ({
      id: r.listingId,
      source: r.source as Listing["source"],
      title: r.title,
      url: r.url,
      image_urls: r.imageUrl ? [r.imageUrl] : [],
      price: r.price,
      currency: r.currency,
      seller: r.seller || null,
      retailer: r.retailer || null,
      tier: (r.tier || null) as Listing["tier"],
      brand: r.brand || null,
      condition: null,
      sizes: [],
      warnings: r.warnings,
      score: r.score ?? null,
      reason: r.reason,
      is_fixture: r.isFixture,
    }));

  // Follows one search to completion. A newer search bumps the token, which stops older loops.
  async function follow(id: string) {
    const token = ++pollToken.current;
    setSearchId(id);
    setJob(null);
    try {
      for (;;) {
        const next = await api.getSearch(`/v1/searches/${id}`);
        if (token !== pollToken.current) return;
        setJob(next);
        if (DONE.has(next.status)) return;
        // The live subscription drives the page; polling picks up the final record (faster if live is down).
        await new Promise((r) => setTimeout(r, isActive ? 4000 : 1500));
      }
    } catch (err) {
      if (token === pollToken.current) setError((err as Error).message);
    }
  }

  useEffect(() => {
    const id = getProfileId();
    setProfileIdState(id);
    if (!id) return;
    refreshBudget(id);
    const thread = loadThread(id);
    setMessages(thread.messages);
    if (thread.searchId) follow(thread.searchId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restore once on load
  }, []);

  async function send(text: string) {
    if (!profileId || !text.trim() || thinking) return;
    setError(null);
    const next: ChatTurn[] = [...messages, { role: "user", text: text.trim() }];
    setMessages(next);
    setThinking(true);
    try {
      const reply = await api.chat(profileId, next);
      const withReply: ChatTurn[] = [
        ...next,
        { role: "agent", text: reply.reply, ...(reply.action === "search" && { brief: reply.brief }) },
      ];
      setMessages(withReply);
      if (reply.budget) setBudget({ linked: true, ...reply.budget });
      saveThread(profileId, { messages: withReply, searchId: reply.search_id ?? searchId });
      if (reply.search_id) follow(reply.search_id);
    } catch (err) {
      setError((err as Error).message);
      setMessages(messages);
    } finally {
      setThinking(false);
    }
  }

  function reset() {
    pollToken.current++;
    setMessages([]);
    setSearchId(null);
    setJob(null);
    if (profileId) saveThread(profileId, { messages: [], searchId: null });
  }

  if (!profileId) {
    return (
      <p className="px-4 mt-10 text-display">
        Build your <Link href="/onboard" className="underline">taste profile</Link> first.
      </p>
    );
  }

  const finished = !!job && DONE.has(job.status);
  const results = finished ? job.results ?? [] : liveListings.length ? liveListings : job?.results ?? [];
  const status = finished ? job.status : liveSearch[0]?.status ?? job?.status;
  const ranked = finished || liveRows.some((r) => r.rank !== undefined);
  const brief = [...messages].reverse().find((m) => m.brief)?.brief;

  return (
    <div className="px-4 mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] items-start">
      <section className="order-2 lg:order-1 min-w-0">
        {!searchId ? (
          <div className="rule-t pt-2">
            <p className="text-display">Tell the agent what you&apos;re looking for.</p>
            <p className="text-sm mt-2 max-w-md">
              Then keep talking: &ldquo;less formal&rdquo;, &ldquo;only black&rdquo;, &ldquo;under $60&rdquo;. Each reply refines the
              search.
            </p>
            <div className="flex flex-wrap gap-2 mt-4">
              {EXAMPLES.map((example) => (
                <button key={example} onClick={() => send(example)} className="label border border-ink px-3 py-2">
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            <SectionTitle aside={job?.ranking_method}>{matchCount(results.length, !finished)}</SectionTitle>
            {brief && <p className="label -mt-1 mb-2 text-muted">For: {brief}</p>}
            {status && !DONE.has(status) && (
              <p className="label mb-3 animate-pulse">
                {results.length
                  ? `${ranked ? "Ranking" : "Comparing them to your taste"}…`
                  : "Searching stores and secondhand sellers…"}
              </p>
            )}
            {job?.warnings?.map((w) => (
              <p key={w} className="label mb-2 text-muted">{w}</p>
            ))}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {results.map((item, i) => (
                <button key={item.id} onClick={() => setSelected(item)} className="text-left">
                  <div className="bg-plinth aspect-[3/4] flex items-center justify-center overflow-hidden">
                    {item.image_urls[0] ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={item.image_urls[0]} alt="" className="max-h-full max-w-full object-contain" />
                    ) : (
                      <span className="label text-muted">{item.is_fixture ? "Demo item" : "No photo"}</span>
                    )}
                  </div>
                  <div className="flex justify-between mt-1 gap-2">
                    <span className="text-display">{i + 1}</span>
                    <span className="label pt-1 text-right">{storeLabel(item)}</span>
                  </div>
                  <p className="text-sm">{item.title}</p>
                  <p className="text-sm">{item.price.toFixed(2)} {item.currency}</p>
                </button>
              ))}
            </div>
          </>
        )}
      </section>

      <ChatPanel
        budget={budget}
        messages={messages}
        thinking={thinking}
        error={error}
        onSend={send}
        onReset={reset}
        className="order-1 lg:order-2"
      />

      <Drawer open={!!selected} onClose={() => setSelected(null)}>
        {selected && searchId && (
          <ListingDetail listing={selected} searchId={searchId} onPurchased={() => refreshBudget()} />
        )}
      </Drawer>
    </div>
  );
}

function ChatPanel({
  budget,
  messages,
  thinking,
  error,
  onSend,
  onReset,
  className,
}: {
  budget: Budget | null;
  messages: ChatTurn[];
  thinking: boolean;
  error: string | null;
  onSend: (text: string) => void;
  onReset: () => void;
  className?: string;
}) {
  const [draft, setDraft] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollIntoView, which React rejects as a cleanup.
    end.current?.scrollIntoView({ block: "end" });
  }, [messages, thinking]);

  function submit() {
    if (!draft.trim() || thinking) return;
    onSend(draft);
    setDraft("");
  }

  return (
    <aside
      className={`${className ?? ""} flex flex-col border border-ink bg-paper h-[60dvh] lg:h-[calc(100dvh-8rem)] lg:sticky lg:top-4`}
    >
      <div className="rule-b flex items-baseline justify-between px-3 py-2">
        <span className="text-display">Ask Niche</span>
        {messages.length > 0 && (
          <button onClick={onReset} className="label underline">New search</button>
        )}
      </div>
      {budget?.linked && <BudgetStrip budget={budget} />}
      <div className="flex-1 overflow-y-auto px-3 py-3 grid gap-3 content-start">
        {messages.length === 0 && (
          <p className="text-sm text-muted">What are you shopping for? Describe it like you would to a friend.</p>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? (
            <p key={i} className="justify-self-end max-w-[85%] bg-plinth px-3 py-2 text-sm">{m.text}</p>
          ) : (
            <div key={i} className="justify-self-start max-w-[85%]">
              <p className="label mb-1">Niche</p>
              {/* Outlined box: reads as a reply next to the user's grey bubbles, in the site's ruled style. */}
              <div className="border border-ink px-3 py-2">
                <p className="text-sm">{m.text}</p>
                {m.brief && <p className="label text-muted mt-1">Searched: {m.brief}</p>}
              </div>
            </div>
          ),
        )}
        {thinking && <p className="label animate-pulse">Niche is thinking…</p>}
        {error && <p className="text-sm">{error}</p>}
        <div ref={end} />
      </div>
      <form
        className="rule-t flex items-end gap-2 px-3 py-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          rows={2}
          className="flex-1 resize-none bg-transparent outline-none text-sm placeholder:text-muted"
          placeholder={messages.length ? "No actually, less formal…" : "I want an asymmetrical buttoned top"}
          value={draft}
          disabled={thinking}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <div className="grid gap-1 justify-items-end">
          <VoiceButton context="shop" label="Talk" onTranscript={onSend} />
          <button disabled={thinking || !draft.trim()} className="label underline disabled:no-underline disabled:text-muted">
            Send
          </button>
        </div>
      </form>
    </aside>
  );
}

const money = (n = 0) => `$${Math.round(n).toLocaleString()}`;
const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** "$95 of $150 clothing this month · $55 left" plus the next bill, from the shopper's mock bank. */
function BudgetStrip({ budget }: { budget: Budget }) {
  const spent = budget.month_spent ?? 0;
  const limit = budget.monthly_budget ?? 0;
  const used = limit ? Math.min(100, (spent / limit) * 100) : 0;
  const bill = budget.upcoming_bills?.[0];
  return (
    <div className="rule-b px-3 py-2 grid gap-1" title="From your linked Capital One (Nessie) demo account">
      <div className="flex justify-between label">
        <span>
          {money(spent)} of {money(limit)} clothing this month
        </span>
        <span>{money(budget.remaining)} left</span>
      </div>
      <div className="h-1 bg-plinth">
        <div className="h-full bg-ink" style={{ width: `${used}%` }} />
      </div>
      <p className="label text-muted">
        Balance {money(budget.balance)}
        {bill && ` · ${bill.payee} ${money(bill.amount)} due ${shortDate(bill.due)}`}
      </p>
    </div>
  );
}

// "Loading matches" → "3 matches so far" → "20 matches".
function matchCount(count: number, loading: boolean) {
  if (loading && count === 0) return "Loading matches";
  const noun = count === 1 ? "match" : "matches";
  return loading ? `${count} ${noun} so far` : `${count} ${noun}`;
}

// "Nordstrom · Department store", "Depop · Secondhand"; older single-marketplace results fall back to seller/source.
function storeLabel(listing: Listing) {
  if (!listing.retailer) return listing.seller ?? listing.source;
  return listing.tier ? `${listing.retailer} · ${TIER_LABELS[listing.tier]}` : listing.retailer;
}

function ListingDetail({
  listing,
  searchId,
  onPurchased,
}: {
  listing: Listing;
  searchId: string;
  onPurchased?: () => void;
}) {
  return (
    <div className="grid gap-4">
      <div>
        <p className="text-display">{listing.title}</p>
        <p className="text-display">{storeLabel(listing)}</p>
        <p className="text-display">{listing.price.toFixed(2)} {listing.currency}</p>
      </div>
      <div className="grid gap-1">
        <span className="label">Why this matches</span>
        <p className="text-sm">{listing.reason}</p>
        {[...new Set(listing.warnings)].map((w) => (
          <p key={w} className="text-xs text-muted">— {w}</p>
        ))}
        {listing.is_fixture ? (
          <p className="label mt-1">Synthetic demo item</p>
        ) : (
          <a href={listing.url} target="_blank" rel="noreferrer" className="label underline mt-1">View on {listing.retailer ?? listing.source} ↗</a>
        )}
      </div>
      <div className="rule-t pt-3">
        <Checkout searchId={searchId} listing={listing} onPurchased={onPurchased} />
      </div>
    </div>
  );
}
