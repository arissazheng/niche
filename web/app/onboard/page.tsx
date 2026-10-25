"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { HandCircle } from "@/components/hand-circle";
import { MeasurementsPanel } from "@/components/measurements";
import { api } from "@/lib/api";
import { SHOPPING, useAssistantSkill } from "@/lib/assistant";
import { clearProfile, getProfileId, setProfileId } from "@/lib/session";
import { SizingSection, emptySizing, withDefaults } from "@/components/sizing";
import "./profile-book.css";
import type { ClothingSizes, HeardOnboarding, Onboarding, SizePick } from "@/lib/types";

const SHOPS = ["Depop", "Etsy", "Poshmark", "Grailed", "Thrift stores", "Vintage shops", "Local boutiques", "Big retailers"];

export default function OnboardPage() {
  const router = useRouter();
  const [form, setForm] = useState<Onboarding>({
    name: "",
    age: null,
    email: "",
    sizing: emptySizing(),
    measurements: { unit: "in" },
    budget_min: 0,
    budget_max: 150,
    currency: "USD",
    usual_shops: [],
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // An existing profile is edited in place; creating a new one would detach its photos and moodboard.
  const [existing, setExisting] = useState<{ id: string; built: boolean } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const formEl = useRef<HTMLFormElement>(null);
  const latest = useRef(form);
  latest.current = form;
  const budgetTalked = useRef(false);

  // The assistant fills this form in conversation: it asks, the shopper answers, the fields fill themselves.
  useAssistantSkill({
    id: "onboarding",
    label: existing ? "Updating your profile" : "Getting to know you",
    intro: existing
      ? "Want to change anything here? Just tell me, like \u201CI'm a medium in tops now\u201D."
      : "Hi, I'm Niche! I'll help you shop your style. Let's get to know each other: what's your name, and where do you usually shop?",
    placeholder: "I\u2019m Dana, I shop on Depop and thrift stores\u2026",
    handle: answered,
  });

  useEffect(() => {
    const id = getProfileId();
    if (!id) return;
    api.getProfile(id).then(
      ({ profile }) => {
        setForm({ ...profile.onboarding, sizing: withDefaults(profile.onboarding.sizing) });
        setExisting({ id, built: profile.version > 0 });
      },
      () => {},
    );
  }, []);

  const toggleShop = (shop: string) =>
    setForm((f) => ({
      ...f,
      usual_shops: f.usual_shops.includes(shop) ? f.usual_shops.filter((s) => s !== shop) : [...f.usual_shops, shop],
    }));

  // An answer (spoken or typed) fills in only the fields it mentions; lists add to what is already picked.
  // Returns what the assistant says back: what it got, then the next thing it needs.
  async function answered(transcript: string): Promise<string | null> {
    if (existing?.built && SHOPPING.test(transcript)) return null; // "find me boots": that's for the shopping agent
    if (/^\s*(save|continue|done|next|i'?m done|that'?s (it|all|everything)|let'?s go)\b/i.test(transcript)) {
      if (!latest.current.data_consent) {
        return "Almost there! Tick the box at the bottom so I can look at your photos with Claude, then say continue.";
      }
      formEl.current?.requestSubmit();
      return existing ? "Saved!" : "Saved! Now show me some looks you love. Drop in photos and I'll tell you what I see.";
    }
    setVoiceNote(`\u201C${transcript}\u201D \u2014 filling in\u2026`);
    const heard: HeardOnboarding = await api.heardOnboarding(transcript, SHOPS);
    const { usual_shops, favorite_brands, measurements, system, sizes, ...rest } = heard;
    const f = latest.current;
    const sizeSystem = system ?? f.sizing.system ?? "womens";
    let sizing = system ? { ...f.sizing, system } : f.sizing;
    if (sizes?.length) {
      const chart = { ...sizing[sizeSystem] };
      for (const size of sizes) {
        const pick = chart[size.category];
        const values = pick.format === size.format ? [...new Set([...pick.values, size.value])] : [size.value];
        chart[size.category] = { ...pick, format: size.format, values };
      }
      sizing = { ...sizing, system: sizeSystem, [sizeSystem]: chart };
    }
    const next: Onboarding = {
      ...f,
      ...rest,
      sizing,
      usual_shops: [...new Set([...f.usual_shops, ...(usual_shops ?? [])])],
      favorite_brands: [...new Set([...(f.favorite_brands ?? []), ...(favorite_brands ?? [])])],
      measurements: { ...(f.measurements ?? { unit: "in" }), ...measurements, unit: measurements?.unit ?? f.measurements?.unit ?? "in" },
    };
    latest.current = next;
    setForm(next);
    if (rest.budget_min !== undefined || rest.budget_max !== undefined) budgetTalked.current = true;
    const filled = [
      rest.name !== undefined && "name",
      rest.age !== undefined && "age",
      rest.email !== undefined && "email",
      (rest.budget_min !== undefined || rest.budget_max !== undefined) && "budget",
      usual_shops?.length && "shops",
      favorite_brands?.length && `brands (${favorite_brands.join(", ")})`,
      (sizes?.length || system) && "sizes",
      measurements && "measurements",
    ].filter(Boolean);
    setVoiceNote(`\u201C${transcript}\u201D \u2014 ${filled.length ? `filled in ${filled.join(", ")}` : "nothing to fill in from that"}.`);
    const ack = rest.name
      ? `Nice to meet you, ${rest.name}!`
      : filled.length
        ? ["Got it.", "Love that.", "Perfect.", "Noted!"][transcript.length % 4]
        : "Hmm, I didn't catch anything to fill in from that.";
    return `${ack} ${nextQuestion(next, budgetTalked.current, !!existing)}`;
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (existing) {
        await api.updateOnboarding(existing.id, form);
        router.push("/upload"); // saved changes go back to the lookbook
        return;
      }
      const { profile } = await api.createProfile(form);
      setProfileId(profile.id);
      router.push("/upload");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  async function deleteData() {
    if (!existing) return;
    setBusy(true);
    try {
      await api.deleteProfile(existing.id);
      clearProfile(existing.id);
      router.push("/");
    } catch (err) {
      setError((err as Error).message);
      setConfirmDelete(false);
      setBusy(false);
    }
  }

  return (
    <form ref={formEl} onSubmit={submit} className="profile-book bg-[#efefef] -mt-px">
      <header className="profile-heading">
        <p className="label">Niche profiles</p>
        <h1 className="text-[clamp(1.8rem,3vw,3rem)] leading-[1.05] tracking-tight font-medium">
          {existing ? "Your profile" : "Let\u2019s get to know you."}
        </h1>
      </header>

      <div className="profile-spread">
        {/* An open encyclopedia: two pages, two ruled columns each, shared decorative images interspersed with entries. */}
        <Book>
          <BookPage side="left" letter="P" number="01" footer="The Niche Profile">
            <Column>
              <div className="book-image-pair">
                <div className="book-plate relative overflow-hidden">
                  <Image src="/images/profile/palm-beach.png" alt="" fill sizes="(max-width: 699px) 45vw, 23vw" className="object-cover object-[center_32%]" />
                </div>
                <Plate />
              </div>
            </Column>
            <Column ruled>
              <Entry title="About you">
                <div className="grid gap-3">
                  <Field label="Name">
                    <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
                  </Field>
                  <div className="grid grid-cols-[5rem_1fr] gap-3">
                    <Field label="Age">
                      <input
                        className="input"
                        type="number"
                        min={13}
                        value={form.age ?? ""}
                        onChange={(e) => setForm({ ...form, age: e.target.value ? Number(e.target.value) : null })}
                      />
                    </Field>
                    <Field label="Email">
                      <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
                    </Field>
                  </div>
                </div>
                <SeeAlso>Lookbook · Taste</SeeAlso>
              </Entry>
            </Column>
            <Column wide>
              <Entry title="Sizes">
                <SizingSection value={form.sizing} onChange={(sizing) => setForm((f) => ({ ...f, sizing }))} />
                <div className="book-plate book-plate-strip relative overflow-hidden">
                  <Image src="/images/profile/church-interior.png" alt="" fill sizes="(max-width: 699px) 90vw, 46vw" className="object-cover object-center" />
                </div>
              </Entry>
            </Column>
          </BookPage>

          <BookPage side="right" letter="P" number="02" footer="An A–Z of Your Taste">
            <Column>
              <Entry title="Everyday outfit budget">
                <div className="flex items-center gap-4">
                  <span className="font-serif text-3xl tabular-nums">${form.budget_max}</span>
                  <input
                    type="range"
                    min={10}
                    max={500}
                    step={5}
                    value={form.budget_max}
                    onChange={(e) => setForm({ ...form, budget_max: Number(e.target.value) })}
                    className="flex-1 accent-ink"
                    aria-label="Maximum price per item"
                  />
                </div>
              </Entry>
              <div className="book-plate book-plate-landscape relative overflow-hidden">
                <Image src="/images/profile/ballet-shoes.png" alt="" fill sizes="(max-width: 699px) 45vw, 23vw" className="object-cover object-bottom" />
              </div>
              <Entry title="Where you usually shop">
                <div className="flex flex-wrap gap-2">
                  {SHOPS.map((shop) => (
                    <button type="button" key={shop} onClick={() => toggleShop(shop)} aria-pressed={form.usual_shops.includes(shop)}>
                      <HandCircle selected={form.usual_shops.includes(shop)}>{shop}</HandCircle>
                    </button>
                  ))}
                </div>
              </Entry>
            </Column>
            <Column ruled>
              <Entry title="Shops near you">
                <label className="flex items-start gap-3 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1 accent-ink"
                    checked={!!form.nearby_shops}
                    onChange={(e) => setForm({ ...form, nearby_shops: e.target.checked })}
                  />
                  <span>
                    Also suggest local shops worth visiting under my search results. Only your ZIP code is used: it&apos;s
                    sent to Google&apos;s Gemini to find shops on Google Maps, never your exact location.
                  </span>
                </label>
                {form.nearby_shops && (
                  <div className="mt-2">
                    <Field label="ZIP code">
                      <input
                        className="input w-32"
                        inputMode="numeric"
                        pattern="\d{5}"
                        maxLength={5}
                        required
                        value={form.zip_code ?? ""}
                        onChange={(e) => setForm({ ...form, zip_code: e.target.value.replace(/\D/g, "").slice(0, 5) })}
                      />
                    </Field>
                  </div>
                )}
              </Entry>
              <div className="book-plate book-plate-portrait relative overflow-hidden">
                <Image src="/images/profile/fashion-board.webp" alt="" fill sizes="(max-width: 699px) 40vw, 20vw" className="object-cover object-[center_28%] scale-[1.35] origin-[center_28%]" />
              </div>
              <Entry title="Before we begin">
                <label className="flex items-start gap-3 text-sm">
                  <input
                    type="checkbox"
                    required
                    className="mt-1 accent-ink"
                    checked={!!form.data_consent}
                    onChange={(e) => setForm({ ...form, data_consent: e.target.checked })}
                  />
                  <span>
                    I agree that my photos and notes are sent to Claude (Anthropic) to build my taste profile. My name,
                    email and age never are. <Link href="/how-it-works#data" className="underline">What Niche keeps</Link>
                  </span>
                </label>
              </Entry>
            </Column>
            <Column wide>
              <Entry title="Measurements">
                {form.sizing.system && (
                  <MeasurementsPanel
                    key={existing?.id ?? "new"} // remount once a saved profile loads, to show its measurements
                    system={form.sizing.system}
                    value={form.measurements ?? { unit: "in" }}
                    onChange={(measurements) => setForm((f) => ({ ...f, measurements }))}
                    onUseSizes={(suggested) =>
                      setForm((f) => {
                        const system = f.sizing.system!;
                        // Only categories the measurements actually point to; everything else stays as picked.
                        const filled = Object.fromEntries(
                          Object.entries(suggested).filter(([k, p]) => k !== "bra" && ((p as SizePick).values?.length || Object.keys((p as SizePick).extras ?? {}).length)),
                        ) as Partial<ClothingSizes>;
                        return { ...f, sizing: { ...f.sizing, [system]: { ...f.sizing[system], ...filled } } };
                      })
                    }
                  />
                )}
                {!form.sizing.system && <p className="text-xs text-muted">Choose a sizing system on the facing page to add optional measurements.</p>}
              </Entry>
            </Column>
          </BookPage>
        </Book>

        {/* Save controls sit below the full-width spread. */}
        <aside className="profile-aside">
          {voiceNote && (
            <p className="text-xs" role="status" aria-live="polite">
              {voiceNote}
            </p>
          )}
          {error && <p className="text-sm">{error}</p>}
          <button disabled={busy} className="justify-self-start border border-ink bg-paper px-5 py-3 text-lg disabled:text-muted">
            {busy ? "Saving…" : existing ? "Save changes" : "Continue"}
          </button>
          {existing && (
            <button type="button" onClick={() => setConfirmDelete(true)} className="label underline justify-self-start text-muted">
              Delete my data
            </button>
          )}
        </aside>
      </div>
      {confirmDelete && <ConfirmDelete busy={busy} onYes={deleteData} onNo={() => setConfirmDelete(false)} />}
    </form>
  );
}

// ---- The book: an open encyclopedia spread ----

/** Dark hardcover with page edges showing on both sides and a soft shadow down the spine. */
function Book({ children }: { children: React.ReactNode }) {
  return (
    <div className="book-cover">
      <div className="book-leaves">
        {children}
        {/* the gutter: pages curving into the binding */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 left-1/2 hidden w-16 -translate-x-1/2 lg:block"
          style={{ background: "linear-gradient(to right, transparent, rgba(0,0,0,.14) 45%, rgba(0,0,0,.2) 50%, rgba(0,0,0,.14) 55%, transparent)" }}
        />
      </div>
    </div>
  );
}

function BookPage({
  side,
  letter,
  number,
  footer,
  children,
}: {
  side: "left" | "right";
  letter: string;
  number: string;
  footer: string;
  children: React.ReactNode;
}) {
  return (
    <section className={`book-page book-page-${side} font-serif`}>
      <div className="book-page-grid">{children}</div>
      {/* letter tab on the outer margin, page number by the spine, running footer */}
      <span className={`absolute top-1/2 -translate-y-1/2 text-lg ${side === "left" ? "left-4" : "right-4"}`}>{letter}</span>
      <span className={`absolute top-1/2 -translate-y-1/2 text-lg ${side === "left" ? "right-4 lg:right-7" : "left-4 lg:left-7"}`}>
        {number}
      </span>
      <p className="absolute bottom-4 inset-x-0 text-center text-[11px] uppercase tracking-[.12em]">{footer}</p>
    </section>
  );
}

/** A text column; `ruled` draws the hairline between columns, `wide` spans the whole page. Big type inside (the
 *  sizing picker's headings) is scaled down to book size. */
function Column({ children, ruled = false, wide = false }: { children: React.ReactNode; ruled?: boolean; wide?: boolean }) {
  return (
    <div
      className={`book-column grid content-start [&_.text-display]:text-lg [&_.text-display]:leading-tight ${
        ruled ? "sm:border-l sm:border-ink/40 sm:pl-3" : ""
      } ${wide ? "sm:col-span-2" : ""}`}
    >
      {children}
    </div>
  );
}

/** An encyclopedia entry: centred serif heading over a hairline, then its body in sans for the form controls. */
function Entry({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="book-entry grid">
      <h2 className="border-t border-ink/50 pt-2 text-center text-xl italic leading-tight">{title}</h2>
      <div className="font-sans">{children}</div>
    </div>
  );
}

/** Shared decorative imagery will replace these fixed grey placeholders. */
function Plate({ variant = "default" }: { variant?: "default" | "landscape" | "portrait" | "strip" }) {
  return <div aria-hidden="true" className={`book-plate book-plate-${variant} bg-[#cfcdc7]`} />;
}

function SeeAlso({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-3 text-center font-serif text-[10px] uppercase leading-tight tracking-[.1em]">
      See also:
      <br />
      {children}
    </p>
  );
}

function ConfirmDelete({ busy, onYes, onNo }: { busy: boolean; onYes: () => void; onNo: () => void }) {
  useEffect(() => {
    const close = (e: KeyboardEvent) => e.key === "Escape" && onNo();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onNo]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4" onClick={onNo}>
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-title"
        className="bg-paper border border-ink p-6 max-w-sm w-full grid gap-4"
        onClick={(e) => e.stopPropagation()}
      >
        <p id="delete-title" className="text-display">Are you sure you want to delete your data?</p>
        <p className="text-sm">
          Your profile, photos, taste profile, searches, chat and bank link are removed from Niche. This can&apos;t be undone.
        </p>
        <div className="grid grid-cols-2 gap-2">
          <button type="button" onClick={onNo} autoFocus className="label border border-ink px-3 py-2">No</button>
          <button type="button" onClick={onYes} disabled={busy} className="label bg-ink text-paper px-3 py-2 disabled:opacity-50">
            {busy ? "Deleting…" : "Yes, delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

/** The next thing the assistant asks for, in the order a friend would. Age and email stay optional. */
function nextQuestion(form: Onboarding, budgetTalked: boolean, existing: boolean) {
  if (existing) return "Anything else to change? Say save when you're done.";
  if (!form.name.trim()) return "What should I call you?";
  if (!form.usual_shops.length) return "Where do you usually shop? Depop, thrift stores, big retailers?";
  const chart = form.sizing.system ? form.sizing[form.sizing.system] : null;
  if (!chart || !(chart.tops.values.length || chart.bottoms.values.length || chart.shoes.values.length)) {
    return "What sizes do you wear? Like a small in tops, a 27 waist, and an 8 in shoes. And is that women's or men's sizing?";
  }
  if (!budgetTalked) return "And what's the most you'd usually spend on one piece?";
  if (!form.data_consent) return "That's everything I need! Tick the box at the bottom so I can look at your photos, then say continue.";
  return "You're all set! Say continue when you're ready.";
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
