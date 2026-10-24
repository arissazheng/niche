"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { SectionTitle } from "@/components/chrome";
import { HandCircle } from "@/components/hand-circle";
import { VoiceButton } from "@/components/voice";
import { api } from "@/lib/api";
import { setProfileId } from "@/lib/session";
import type { Onboarding, SizeLabel } from "@/lib/types";

const SIZES: SizeLabel[] = ["XS", "S", "M", "L", "XL", "XXL"];
const SHOPS = ["Depop", "Etsy", "Poshmark", "Grailed", "Thrift stores", "Vintage shops", "Local boutiques", "Big retailers"];
type SizeSlot = "top" | "bottom" | "outerwear";

export default function OnboardPage() {
  const router = useRouter();
  const [form, setForm] = useState<Onboarding>({
    name: "",
    age: null,
    email: "",
    sizes: { top: null, bottom: null, outerwear: null, shoe: null },
    budget_min: 0,
    budget_max: 150,
    currency: "USD",
    usual_shops: [],
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setSize = (slot: SizeSlot, size: SizeLabel) =>
    setForm((f) => ({ ...f, sizes: { ...f.sizes, [slot]: f.sizes[slot] === size ? null : size } }));
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
        <h1 className="text-display">Let&apos;s get to know you.</h1>
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
              <span className="label w-24">{slot}</span>
              {SIZES.map((size) => (
                <button type="button" key={size} onClick={() => setSize(slot, size)} aria-pressed={form.sizes[slot] === size}>
                  <HandCircle selected={form.sizes[slot] === size}>{size}</HandCircle>
                </button>
              ))}
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
          {busy ? "Saving…" : "Continue"}
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
