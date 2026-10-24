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
import { TIER_LABELS, type Budget, type ChatTurn, type Listing, type SearchCounts, type SearchJob } from "@/lib/types";

const DONE = new Set(["completed", "partial", "failed", "interrupted"]);
// Tap-to-ask starters in the chat: before the first message, then once results are on screen.
const STARTERS = ["Find me black knee-high boots under $120", "Find me a vintage leather jacket", "Find me an asymmetrical buttoned top"];
const FOLLOW_UPS = ["Compare #1 and #2", "Which is the best value?", "Which fits my style best?"];

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
  const [kind, setKind] = useState<Kind>("all");
  const [error, setError] = useState<string | null>(null);
  const [searchId, setSearchId] = useState<string | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  // Off by default: searches use the shopper's own price limits until they ask to stay inside the monthly budget.
  const [keepToBudget, setKeepToBudget] = useState(false);
  useEffect(() => {
    try {
      setKeepToBudget(localStorage.getItem("keep-to-budget") === "1");
    } catch {
      // storage blocked: stays off
    }
  }, []);
  const toggleBudget = (on: boolean) => {
    setKeepToBudget(on);
    try {
      localStorage.setItem("keep-to-budget", on ? "1" : "0");
    } catch {
      // storage blocked: applies to this visit only
    }
  };
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
      // The current search lets the agent answer questions like "what about #2?".
      const reply = await api.chat(profileId, next, searchId, keepToBudget);
      const agentTurn: ChatTurn = { role: "agent", text: reply.reply };
      if (reply.linked?.length) agentTurn.linked = reply.linked;
      if (reply.action === "search") agentTurn.brief = reply.brief;
      if (reply.action === "propose") {
        agentTurn.proposed = reply.brief;
        agentTurn.proposed_price = reply.max_item_price ?? null;
        agentTurn.proposed_size = reply.size ?? null;
        agentTurn.proposed_must_have = reply.must_have?.length ? reply.must_have : null;
        agentTurn.proposed_category = reply.category ?? null;
      }
      const withReply: ChatTurn[] = [...next, agentTurn];
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

  // "Yes, search": run the outstanding proposal directly; no need to ask the model again.
  async function accept(proposal: ChatTurn) {
    if (!profileId || !proposal.proposed || thinking) return;
    setError(null);
    const price = proposal.proposed_price ? ` under $${Math.round(proposal.proposed_price)}` : "";
    const size = proposal.proposed_size ? ` in size ${proposal.proposed_size}` : "";
    const next: ChatTurn[] = [
      ...messages,
      { role: "user", text: "Yes, search for that" },
      { role: "agent", text: `Searching for ${proposal.proposed}${size}${price}.`, brief: proposal.proposed },
    ];
    setMessages(next);
    try {
      const { search_id } = await api.search(profileId, proposal.proposed, {
        maxItemPrice: proposal.proposed_price,
        size: proposal.proposed_size,
        mustHave: proposal.proposed_must_have,
        category: proposal.proposed_category,
      });
      saveThread(profileId, { messages: next, searchId: search_id });
      follow(search_id);
    } catch (err) {
      setError((err as Error).message);
      setMessages(messages);
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
  const allResults = finished ? job.results ?? [] : liveListings.length ? liveListings : job?.results ?? [];
  const results = kind === "all" ? allResults : allResults.filter((item) => kindOf(item) === kind);
  const status = finished ? job.status : liveSearch[0]?.status ?? job?.status;
  const ranked = finished || liveRows.some((r) => r.rank !== undefined);

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
          </div>
        ) : (
          <>
            <SectionTitle aside={job?.ranking_method}>{matchCount(results.length, !finished)}</SectionTitle>
            <p className="label mb-3">
              No sponsored results · ranked by fit to your taste, size and budget ·{" "}
              <Link href="/how-it-works" className="underline">How ranking works</Link>
            </p>
            {finished && job.counts && <Impact counts={job.counts} results={allResults} />}
            <MixFilter results={allResults} kind={kind} onChange={setKind} />
            {status && !DONE.has(status) && (
              <p className="label mb-3 animate-pulse">
                {results.length
                  ? `${ranked ? "Ranking" : "Comparing them to your taste"}…`
                  : "Searching stores and secondhand sellers, then checking each photo against your request…"}
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
                      <img src={item.image_urls[0]} alt="" className="h-full w-full object-contain" />
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
        onAccept={accept}
        onReset={reset}
        hasResults={finished && allResults.length > 1}
        keepToBudget={keepToBudget}
        onToggleBudget={toggleBudget}
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
  onAccept,
  onReset,
  hasResults,
  keepToBudget,
  onToggleBudget,
  className,
}: {
  budget: Budget | null;
  messages: ChatTurn[];
  thinking: boolean;
  error: string | null;
  onSend: (text: string) => void;
  onAccept: (proposal: ChatTurn) => void;
  onReset: () => void;
  hasResults: boolean;
  keepToBudget: boolean;
  onToggleBudget: (on: boolean) => void;
  className?: string;
}) {
  const [draft, setDraft] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const pending = outstandingProposal(messages);
  const last = messages.at(-1);
  // Starters until the shopper types; follow-ups right after a search finishes, until they ask something else.
  const suggestions = thinking
    ? []
    : messages.length === 0
      ? STARTERS
      : hasResults && last?.role === "agent" && last.brief
        ? FOLLOW_UPS
        : [];
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
      {budget?.linked && <BudgetStrip budget={budget} keepToBudget={keepToBudget} onToggle={onToggleBudget} />}
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
                {m.linked?.map((page) => (
                  <p key={page.url} className="label text-muted mb-1">
                    {page.readable ? `Read: ${page.title ?? page.site}` : `Couldn't open ${page.site ?? "that link"}`}
                  </p>
                ))}
                <p className="text-sm">{m.text}</p>
                {m.brief && <p className="label text-muted mt-1">Searched: {m.brief}</p>}
                {m === pending && !thinking && (
                  <div className="flex gap-3 mt-2">
                    <button onClick={() => onAccept(m)} className="label bg-ink text-paper px-3 py-1.5">
                      Yes, search
                    </button>
                    <button onClick={() => input.current?.focus()} className="label underline">
                      Not quite
                    </button>
                  </div>
                )}
              </div>
            </div>
          ),
        )}
        {suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {suggestions.map((text) => (
              <button key={text} onClick={() => onSend(text)} className="label border border-ink px-3 py-1.5 text-left">
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
          submit();
        }}
      >
        <textarea
          ref={input}
          rows={2}
          className="flex-1 resize-none bg-transparent outline-none text-sm placeholder:text-muted"
          placeholder={
            pending ? "Yes, or say what to change…" : messages.length ? "No actually, less formal…" : "I want an asymmetrical buttoned top"
          }
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

/** The latest search the agent offered that hasn't been run yet, matching the backend's rule. */
function outstandingProposal(messages: ChatTurn[]) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "agent") continue;
    if (m.brief) return null;
    if (m.proposed) return m;
  }
  return null;
}

const money = (n = 0) => `$${Math.round(n).toLocaleString()}`;
const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

/** "$95 of $150 clothing this month · $55 left" plus the next bill, from the shopper's mock bank. */
function BudgetStrip({
  budget,
  keepToBudget,
  onToggle,
}: {
  budget: Budget;
  keepToBudget: boolean;
  onToggle: (on: boolean) => void;
}) {
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
      <div className="flex items-center justify-between gap-2">
        <p className="label text-muted">
          Balance {money(budget.balance)}
          {bill && ` · ${bill.payee} ${money(bill.amount)} due ${shortDate(bill.due)}`}
        </p>
        <button
          type="button"
          role="switch"
          aria-checked={keepToBudget}
          onClick={() => onToggle(!keepToBudget)}
          className={`label border border-ink px-2 py-0.5 shrink-0 ${keepToBudget ? "bg-ink text-paper" : ""}`}
          title="When on, searches stay within what's left of your monthly clothing budget"
        >
          Keep to budget: {keepToBudget ? "on" : "off"}
        </button>
      </div>
    </div>
  );
}

// "Looked through 214 listings · left out 31 in the wrong size and 18 over $60 · average $38, $22 under your cap".
function Impact({ counts, results }: { counts: SearchCounts; results: Listing[] }) {
  const out = counts.left_out ?? {};
  const cap = counts.max_item_price;
  const reasons = [
    out.wrong_size && `${out.wrong_size} in the wrong size`,
    out.over_price && `${out.over_price} over ${cap ? money(cap) : "your cap"}`,
    out.sold && `${out.sold} already sold`,
  ].filter(Boolean) as string[];
  const average = results.length ? results.reduce((sum, item) => sum + item.price, 0) / results.length : 0;
  const parts = [
    `Looked through ${counts.retrieved.toLocaleString()} listings`,
    reasons.length > 0 && `left out ${reasons.length > 1 ? `${reasons.slice(0, -1).join(", ")} and ${reasons.at(-1)}` : reasons[0]}`,
    results.length > 0 && `average ${money(average)}${cap && cap > average ? `, ${money(cap - average)} under your cap` : ""}`,
  ].filter(Boolean);
  return <p className="label mb-3">{parts.join(" · ")}</p>;
}

// "Loading matches" → "3 matches so far" → "20 matches".
// "new" covers every store in the retailer bank (the mainstream actor); "secondhand" covers resale apps, small shops
// and independent labels' own stores (the indie actor).
type Kind = "all" | "secondhand" | "new";
const kindOf = (item: Listing): Kind => (item.source === "mainstream" ? "new" : "secondhand");

function MixFilter({ results, kind, onChange }: { results: Listing[]; kind: Kind; onChange: (kind: Kind) => void }) {
  if (!results.length) return null;
  const count = (k: Kind) => (k === "all" ? results.length : results.filter((item) => kindOf(item) === k).length);
  const options: [Kind, string][] = [["all", "All"], ["secondhand", "Secondhand & small shops"], ["new", "New from stores"]];
  return (
    <div className="flex flex-wrap gap-2 mb-3" role="group" aria-label="Show">
      {options.map(([k, label]) => (
        <button
          key={k}
          onClick={() => onChange(k)}
          aria-pressed={kind === k}
          className={`label border border-ink px-3 py-1 ${kind === k ? "bg-ink text-paper" : ""}`}
        >
          {label} {count(k)}
        </button>
      ))}
    </div>
  );
}

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
      </div>
      {!!listing.risks?.length && (
        <div role="alert" className="border-2 border-ink p-3 grid gap-1">
          <span className="label">⚠ Before you buy</span>
          {listing.risks.map((risk) => (
            <p key={risk} className="text-sm">{risk}</p>
          ))}
        </div>
      )}
      <div className="grid gap-1">
        <span className="label">Why this matches</span>
        <p className="text-sm">{listing.reason}</p>
        {[...new Set(listing.warnings)].map((w) => (
          <p key={w} className="text-xs text-muted">— {w}</p>
        ))}
      </div>
      <div className="rule-t pt-3">
        <Checkout searchId={searchId} listing={listing} onPurchased={onPurchased} />
      </div>
    </div>
  );
}
