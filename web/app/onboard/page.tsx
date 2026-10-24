"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { SectionTitle } from "@/components/chrome";
import { HandCircle } from "@/components/hand-circle";
import { MeasurementsPanel } from "@/components/measurements";
import { VoiceButton } from "@/components/voice";
import { api } from "@/lib/api";
import { getProfileId, setProfileId } from "@/lib/session";
import type { Length, Onboarding, SizeLabel } from "@/lib/types";

const SIZES: SizeLabel[] = ["XS", "S", "M", "L", "XL", "XXL"];
// US numbered sizes for pants and skirts, 00 through 40 (misses through plus).
const NUMBERED = ["00", "0", ...Array.from({ length: 20 }, (_, i) => String((i + 1) * 2))];
const LENGTHS: [Length, string][] = [["short", "Short (petite)"], ["regular", "Regular"], ["long", "Long (tall)"]];
const SHOPS = ["Depop", "Etsy", "Poshmark", "Grailed", "Thrift stores", "Vintage shops", "Local boutiques", "Big retailers"];
type SizeSlot = "top" | "bottom" | "outerwear";

export default function OnboardPage() {
  const router = useRouter();
  const [form, setForm] = useState<Onboarding>({
    name: "",
    age: null,
    email: "",
    sizes: { top: null, bottom: null, outerwear: null, shoe: null },
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

  useEffect(() => {
    const id = getProfileId();
    if (!id) return;
    api.getProfile(id).then(
      ({ profile }) => {
        setForm(profile.onboarding);
        setExisting({ id, built: profile.version > 0 });
      },
      () => {},
    );
  }, []);

  const setSize = (slot: SizeSlot, size: string) =>
    setForm((f) => ({ ...f, sizes: { ...f.sizes, [slot]: f.sizes[slot] === size ? null : size } }));
  const setLength = (length: Length) =>
    setForm((f) => ({ ...f, sizes: { ...f.sizes, bottom_length: f.sizes.bottom_length === length ? null : length } }));
  const toggleShop = (shop: string) =>
    setForm((f) => ({
      ...f,
      usual_shops: f.usual_shops.includes(shop) ? f.usual_shops.filter((s) => s !== shop) : [...f.usual_shops, shop],
    }));

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

  return (
    <form onSubmit={submit} className="px-4 grid gap-10 md:grid-cols-[1fr_2fr] mt-6">
      <aside className="md:sticky md:top-4 self-start">
        <h1 className="text-display">{existing ? "Your profile" : "Let\u2019s get to know you."}</h1>
        <p className="text-sm mt-2 max-w-xs">
          Talk it through with the voice agent, or tap your answers. You can change everything later.
        </p>
        <div className="mt-4">
          <VoiceButton context="onboarding" label="Answer out loud" onTranscript={() => {}} />
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
          {(["top", "bottom", "outerwear"] as SizeSlot[]).map((slot) => (
            <div key={slot} className="flex flex-wrap items-center gap-2 py-1">
              <span className="label w-24">{slot === "bottom" ? "Pants & skirts" : slot}</span>
              {SIZES.map((size) => (
                <button type="button" key={size} onClick={() => setSize(slot, size)} aria-pressed={form.sizes[slot] === size}>
                  <HandCircle selected={form.sizes[slot] === size}>{size}</HandCircle>
                </button>
              ))}
              {slot === "bottom" && (
                <>
                  <span className="label w-full sm:w-auto sm:pl-4 text-muted">or your number</span>
                  <div className="flex flex-wrap gap-1 w-full pl-0 sm:pl-24">
                    {NUMBERED.map((size) => (
                      <button type="button" key={size} onClick={() => setSize("bottom", size)} aria-pressed={form.sizes.bottom === size}>
                        <HandCircle selected={form.sizes.bottom === size}>{size}</HandCircle>
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 w-full sm:pl-24">
                    <span className="label text-muted">Length</span>
                    {LENGTHS.map(([length, label]) => (
                      <button type="button" key={length} onClick={() => setLength(length)} aria-pressed={form.sizes.bottom_length === length}>
                        <HandCircle selected={form.sizes.bottom_length === length}>{label}</HandCircle>
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          ))}
          <div className="flex items-center gap-2 py-1">
            <span className="label w-24">Shoe</span>
            <input
              className="input w-20"
              value={form.sizes.shoe ?? ""}
              onChange={(e) => setForm({ ...form, sizes: { ...form.sizes, shoe: e.target.value || null } })}
            />
          </div>
          <MeasurementsPanel
            key={existing?.id ?? "new"} // remount once a saved profile loads, to show its measurements
            value={form.measurements ?? { unit: "in" }}
            onChange={(measurements) => setForm((f) => ({ ...f, measurements }))}
            onUseSizes={(suggested) =>
              setForm((f) => ({
                ...f,
                sizes: { ...f.sizes, ...Object.fromEntries(Object.entries(suggested).filter(([, v]) => v != null)) },
              }))
            }
          />
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

        {error && <p className="text-sm">{error}</p>}
        <button disabled={busy} className="rule-t rule-b text-display py-2 w-full disabled:text-muted">
          {busy ? "Saving…" : existing ? "Save changes" : "Continue"}
        </button>
      </div>
    </form>
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
