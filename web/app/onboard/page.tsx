"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { SectionTitle } from "@/components/chrome";
import { HandCircle } from "@/components/hand-circle";
import { MeasurementsPanel } from "@/components/measurements";
import { VoiceButton } from "@/components/voice";
import { api } from "@/lib/api";
import { clearProfile, getProfileId, setProfileId } from "@/lib/session";
import { SizingSection, emptySizing, withDefaults } from "@/components/sizing";
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

  // A spoken answer fills in only the fields it mentions; lists add to what is already picked.
  async function answered(transcript: string) {
    setVoiceNote(`\u201C${transcript}\u201D \u2014 filling in\u2026`);
    try {
      const heard: HeardOnboarding = await api.heardOnboarding(transcript, SHOPS);
      const { usual_shops, favorite_brands, measurements, ...rest } = heard;
      setForm((f) => ({
        ...f,
        ...rest,
        usual_shops: [...new Set([...f.usual_shops, ...(usual_shops ?? [])])],
        favorite_brands: [...new Set([...(f.favorite_brands ?? []), ...(favorite_brands ?? [])])],
        measurements: { ...(f.measurements ?? { unit: "in" }), ...measurements, unit: measurements?.unit ?? f.measurements?.unit ?? "in" },
      }));
      const filled = [
        rest.name !== undefined && "name",
        rest.age !== undefined && "age",
        rest.email !== undefined && "email",
        (rest.budget_min !== undefined || rest.budget_max !== undefined) && "budget",
        usual_shops?.length && "shops",
        favorite_brands?.length && `brands (${favorite_brands.join(", ")})`,
        measurements && "measurements",
      ].filter(Boolean);
      setVoiceNote(
        `\u201C${transcript}\u201D \u2014 ${filled.length ? `filled in ${filled.join(", ")}` : "nothing to fill in from that"}. Sizes are picked below.`,
      );
    } catch (err) {
      setVoiceNote(`Couldn\u2019t use that answer: ${(err as Error).message}`);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (existing) {
        await api.updateOnboarding(existing.id, form);
        router.push(existing.built ? "/shop" : "/upload");
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
    <form onSubmit={submit} className="px-4 grid gap-10 md:grid-cols-[1fr_2fr] mt-6">
      <aside className="md:sticky md:top-4 self-start">
        <h1 className="text-display">{existing ? "Your profile" : "Let\u2019s get to know you."}</h1>
        <p className="text-sm mt-2 max-w-xs">
          Talk it through with the voice agent, or tap your answers. You can change everything later.
        </p>
        <div className="mt-4">
          <VoiceButton context="onboarding" label="Answer out loud" onTranscript={answered} />
          <p className="text-xs text-muted mt-2 max-w-xs">
            {"Try: \u201CI\u2019m Dana, 25, I shop on Depop and thrift stores, budget up to $120.\u201D"}
          </p>
          {voiceNote && (
            <p className="text-xs mt-2 max-w-xs" role="status" aria-live="polite">
              {voiceNote}
            </p>
          )}
        </div>
      </aside>

      <div className="grid gap-8">
        <section>
          <SectionTitle aside="01">About you</SectionTitle>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Name">
              <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
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
        </section>

        <section>
          <SectionTitle aside="02">Sizes</SectionTitle>
          <SizingSection value={form.sizing} onChange={(sizing) => setForm((f) => ({ ...f, sizing }))} />
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
        </section>

        <section>
          <SectionTitle aside="03">Everyday outfit budget</SectionTitle>
          <div className="flex items-center gap-4">
            <span className="text-display tabular-nums">${form.budget_max}</span>
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
        </section>

        <section>
          <SectionTitle aside="04">Where do you usually shop?</SectionTitle>
          <div className="flex flex-wrap gap-2">
            {SHOPS.map((shop) => (
              <button type="button" key={shop} onClick={() => toggleShop(shop)} aria-pressed={form.usual_shops.includes(shop)}>
                <HandCircle selected={form.usual_shops.includes(shop)}>{shop}</HandCircle>
              </button>
            ))}
          </div>
        </section>

        <label className="flex items-start gap-3 text-sm">
          <input
            type="checkbox"
            required
            className="mt-1 accent-ink"
            checked={!!form.data_consent}
            onChange={(e) => setForm({ ...form, data_consent: e.target.checked })}
          />
          <span>
            I agree that my photos and notes are sent to Claude (Anthropic) to build my taste profile. My name, email
            and age never are. <Link href="/how-it-works#data" className="underline">What Niche keeps</Link>
          </span>
        </label>

        {error && <p className="text-sm">{error}</p>}
        <button disabled={busy} className="rule-t rule-b text-display py-2 w-full disabled:text-muted">
          {busy ? "Saving…" : existing ? "Save changes" : "Continue"}
        </button>
        {existing && (
          <button type="button" onClick={() => setConfirmDelete(true)} className="label underline justify-self-center">
            Delete my data
          </button>
        )}
      </div>
      {confirmDelete && <ConfirmDelete busy={busy} onYes={deleteData} onNo={() => setConfirmDelete(false)} />}
    </form>
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="grid gap-1">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}
