"use client";

import { useEffect, useState } from "react";
import { HandCircle } from "@/components/hand-circle";
import { api } from "@/lib/api";
import type {
  AccessoryCategory,
  ClothingCategory,
  ClothingSizes,
  SizeCatalog,
  SizeCategorySpec,
  SizePick,
  SizeRegion,
  SizeSystem,
  Sizing,
} from "@/lib/types";

const EMPTY: SizePick = { format: null, values: [], extras: {} };
const emptyClothing = (): ClothingSizes => ({
  tops: EMPTY, bottoms: EMPTY, dresses: EMPTY, outerwear: EMPTY, shoes: EMPTY, bra: {},
});
export const emptySizing = (): Sizing => ({
  system: null,
  region: "us",
  womens: emptyClothing(),
  mens: emptyClothing(),
  accessories: { belts: EMPTY, hats: EMPTY, gloves: EMPTY, rings: EMPTY },
});

/** Fills gaps in a saved (or partial) sizing so every category has a pick to edit. */
export function withDefaults(sizing?: Partial<Sizing> | null): Sizing {
  const base = emptySizing();
  const clothing = (c?: Partial<ClothingSizes>) => ({ ...emptyClothing(), ...c });
  return {
    system: sizing?.system ?? null,
    region: sizing?.region ?? "us",
    womens: clothing(sizing?.womens),
    mens: clothing(sizing?.mens),
    accessories: { ...base.accessories, ...sizing?.accessories },
  };
}

const SYSTEMS: [SizeSystem, string, string][] = [
  ["womens", "Women's sizing", "Tops, bottoms, dresses & skirts, outerwear, shoes"],
  ["mens", "Men's sizing", "Tops, bottoms, outerwear, shoes"],
];
const CLOTHING: ClothingCategory[] = ["tops", "bottoms", "dresses", "outerwear", "shoes"];
const ACCESSORIES: AccessoryCategory[] = ["belts", "hats", "gloves", "rings"];

/**
 * Size preferences, drawn from the backend catalog (backend/taste/sizing.py). The system only decides which charts
 * show; women's and men's picks are kept separately so switching back restores them.
 */
export function SizingSection({ value, onChange }: { value: Sizing; onChange: (next: Sizing) => void }) {
  const [catalog, setCatalog] = useState<SizeCatalog | null>(null);
  const [showDresses, setShowDresses] = useState(false);
  const [accessoriesOpen, setAccessoriesOpen] = useState(false);
  useEffect(() => {
    api.sizingCatalog().then(setCatalog, () => setCatalog(null));
  }, []);

  // Options are visible straight away (women's by default); choosing the other chart switches them.
  const system = value.system ?? "womens";
  const sizes = system ? value[system] : null;
  const anyAccessory = ACCESSORIES.some((a) => value.accessories[a].values.length);
  useEffect(() => {
    if (anyAccessory) setAccessoriesOpen(true);
  }, [anyAccessory]);

  const setClothing = (category: ClothingCategory, pick: SizePick) =>
    onChange({ ...value, system, [system]: { ...value[system], [category]: pick } });
  const setAccessory = (category: AccessoryCategory, pick: SizePick) =>
    onChange({ ...value, accessories: { ...value.accessories, [category]: pick } });

  return (
    <div className="sizing-section grid gap-6">
      <div>
        <p className="text-display">Which sizing do you usually shop in?</p>
        <p className="text-sm mt-1 max-w-lg">
          We&apos;ll use this to show you the right size options. You can still discover clothing from any department.
        </p>
        <div className="grid grid-cols-2 gap-3 mt-3" role="radiogroup" aria-label="Sizing system">
          {SYSTEMS.map(([id, label, covers]) => (
            <button
              key={id}
              type="button"
              role="radio"
              aria-checked={system === id}
              onClick={() => onChange({ ...value, system: id })}
              className={`border border-ink text-left p-4 transition-colors ${
                system === id ? "bg-ink text-paper" : "hover:bg-plinth"
              }`}
            >
              <span className="text-display block">{label}</span>
              <span className={`text-xs mt-1 block ${system === id ? "" : "text-muted"}`}>{covers}</span>
            </button>
          ))}
        </div>
      </div>

      {system && catalog && (
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
          <span className="label">Size region</span>
          <div className="flex flex-wrap gap-x-3 text-sm" role="radiogroup" aria-label="Size region">
            {catalog.regions.map((r) => (
              <button
                key={r.id}
                type="button"
                role="radio"
                aria-checked={value.region === r.id}
                onClick={() => onChange({ ...value, region: r.id })}
                className={value.region === r.id ? "underline underline-offset-4 decoration-1" : "text-muted hover:text-ink"}
              >
                {r.label}
              </button>
            ))}
          </div>
          <span className="text-xs text-muted basis-full">Shows that country&apos;s size charts first. Letter sizes work everywhere.</span>
        </div>
      )}

      {system && sizes && catalog && (
        <div className="sizing-categories grid">
          {CLOTHING.map((category) => {
            const spec = catalog[system][category];
            const hidden = spec.optional && !showDresses && !sizes[category].values.length;
            if (hidden) return null;
            return (
              <CategoryRow
                key={`${system}-${category}`}
                region={value.region}
                spec={spec}
                pick={sizes[category]}
                onChange={(pick) => setClothing(category, pick)}
              />
            );
          })}
          {catalog[system].dresses.optional && !showDresses && !sizes.dresses.values.length && (
            <button type="button" onClick={() => setShowDresses(true)} className="label underline underline-offset-2 justify-self-start py-2 text-muted hover:text-ink">
              + Dresses & skirts
            </button>
          )}
          {system === "womens" && (
            <BraRow
              charts={catalog.bra.regions}
              region={value.region}
              regionLabel={catalog.regions.find((r) => r.id === value.region)?.label ?? "US"}
              value={sizes.bra}
              onChange={(bra) => onChange({ ...value, womens: { ...value.womens, bra } })}
            />
          )}
        </div>
      )}
      {system && !catalog && <p className="label text-muted">Loading sizes…</p>}

      {system && catalog && (
        <div className="rule-t pt-3">
          {!accessoriesOpen ? (
            <button type="button" onClick={() => setAccessoriesOpen(true)} className="text-left group">
              <span className="label underline underline-offset-2 group-hover:no-underline">+ Add accessory sizing</span>
              <span className="text-xs text-muted block mt-0.5">For those little details.</span>
            </button>
          ) : (
            <div className="grid">
              <div className="flex items-baseline justify-between">
                <span className="label">Accessory sizing</span>
                <button type="button" onClick={() => setAccessoriesOpen(false)} className="text-xs text-muted underline hover:text-ink">
                  Hide
                </button>
              </div>
              {ACCESSORIES.map((category) => (
                <CategoryRow
                  key={category}
                  compact
                  region={value.region}
                  spec={catalog.accessories[category]}
                  pick={value.accessories[category]}
                  onChange={(pick) => setAccessory(category, pick)}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** One category: label and hint, a quiet chart switcher, the sizes (several allowed), and optional extras. */
function CategoryRow({
  spec,
  pick,
  region,
  onChange,
  compact = false,
}: {
  spec: SizeCategorySpec;
  pick: SizePick;
  region: SizeRegion;
  onChange: (pick: SizePick) => void;
  compact?: boolean;
}) {
  // This region's charts, plus any chart already holding the shopper's sizes (so a region change never hides them).
  const inRegion = (f: { regions?: SizeRegion[] }) => !f.regions || f.regions.includes(region);
  const formats = spec.formats.filter((f) => spec.every_region || inRegion(f) || f.id === pick.format);
  const opening = (spec.every_region && formats.find((f) => f.regions?.includes(region))) || formats[0];
  const format = formats.find((f) => f.id === pick.format) ?? opening;
  const values = pick.format === format.id ? pick.values : [];
  const extras = (spec.extras ?? []).filter(
    (e) => (!e.formats || e.formats.includes(format.id)) && (inRegion(e) || pick.extras[e.id]),
  );
  const typed = values.filter((v) => !format.options.includes(v));
  const filled = values.length > 0 || Object.keys(pick.extras).length > 0;
  const [opened, setOpened] = useState<string[]>([]);
  // A tucked group stays behind its link until opened, or while any of its fields has a value.
  const groups = [...new Set(extras.map((e) => e.tucked).filter((g): g is string => !!g))];
  const tucked = groups.filter((g) => !opened.includes(g) && !extras.some((e) => e.tucked === g && pick.extras[e.id]));
  const shown = extras.filter((e) => !e.tucked || !tucked.includes(e.tucked));

  const toggle = (size: string) =>
    onChange({
      format: format.id,
      values: values.includes(size) ? values.filter((v) => v !== size) : [...values, size].slice(0, 8),
      extras: pick.extras,
    });
  const setExtra = (id: string, v: string | null) => {
    const next = { ...pick.extras };
    if (v === null || next[id] === v) delete next[id];
    else next[id] = v;
    onChange({ format: format.id, values, extras: next });
  };

  return (
    <div className={`sizing-category grid sm:grid-cols-[11rem_1fr] gap-x-4 gap-y-1 rule-t ${compact ? "py-2" : "py-3"}`}>
      <div>
        <p className={compact ? "label" : "label pt-0.5"}>{spec.label}</p>
        {spec.hint && !compact && <p className="text-xs text-muted mt-0.5 max-w-[11rem]">{spec.hint}</p>}
        {filled && (
          <button type="button" onClick={() => onChange({ format: null, values: [], extras: {} })} className="text-xs text-muted underline hover:text-ink mt-1">
            Clear
          </button>
        )}
      </div>
      <div className="grid gap-1.5">
        {formats.length > 1 && (
          <div className="flex flex-wrap gap-x-3 text-xs" role="tablist" aria-label={`${spec.label} size chart`}>
            {formats.map((f) => (
              <button
                key={f.id}
                type="button"
                role="tab"
                aria-selected={f.id === format.id}
                onClick={() => f.id !== format.id && onChange({ format: f.id, values: [], extras: pick.extras })}
                className={f.id === format.id ? "underline underline-offset-4 decoration-1" : "text-muted hover:text-ink"}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}
        <Options options={[...format.options, ...typed]} selected={values} onPick={toggle} dense={format.options.length > 12}>
          {format.custom && (
            <TypeIn label={`Other ${format.label.toLowerCase()}`} range={format.custom} onAdd={(v) => !values.includes(v) && toggle(v)} />
          )}
        </Options>
        {shown.map((extra) => (
          <div key={extra.id} className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="text-xs text-muted w-full sm:w-auto">{extra.label}</span>
            <Options
              options={[...extra.options, ...(pick.extras[extra.id] && !extra.options.includes(pick.extras[extra.id]) ? [pick.extras[extra.id]] : [])]}
              selected={pick.extras[extra.id] ? [pick.extras[extra.id]] : []}
              onPick={(v) => setExtra(extra.id, v)}
              dense
            >
              {extra.custom && <TypeIn label={`Other ${extra.label.toLowerCase()}`} range={extra.custom} onAdd={(v) => setExtra(extra.id, v)} />}
            </Options>
          </div>
        ))}
        {tucked.map((link) => (
          <button key={link} type="button" onClick={() => setOpened((o) => [...o, link])} className="text-xs text-muted underline hover:text-ink justify-self-start">
            + {link}
          </button>
        ))}
      </div>
    </div>
  );
}

function BraRow({
  charts,
  region,
  regionLabel,
  value,
  onChange,
}: {
  charts: SizeCatalog["bra"]["regions"];
  region: SizeRegion;
  regionLabel: string;
  value: ClothingSizes["bra"];
  onChange: (bra: ClothingSizes["bra"]) => void;
}) {
  // A saved size keeps its own notation (cups aren't converted between regions); an empty one follows the region.
  const notation = value.band || value.cup ? value.notation ?? "us" : region;
  const spec = charts[notation];
  const [more, setMore] = useState(spec.cups_extended.includes(value.cup ?? ""));
  const cups = more ? [...spec.cups, ...spec.cups_extended] : spec.cups;
  const set = (key: "band" | "cup", v: string) =>
    onChange({ ...value, notation, [key]: value[key] === v ? null : v });
  return (
    <div className="sizing-bra grid sm:grid-cols-[11rem_1fr] gap-x-4 gap-y-1 rule-t py-3 text-sm">
      <div>
        <p className="text-sm text-muted">Bra size (optional)</p>
        {value.band && value.cup && <p className="text-xs mt-0.5">{value.band}{value.cup} {notation === "asia" ? "Japan" : notation.toUpperCase()}</p>}
        {notation !== region && (
          <button type="button" onClick={() => onChange({ notation: region })} className="text-xs text-muted underline hover:text-ink mt-0.5 text-left">
            Use {regionLabel} sizes
          </button>
        )}
      </div>
      <div className="grid gap-1">
        <div className="flex flex-wrap items-center gap-x-2">
          <span className="text-xs text-muted w-10">Band</span>
          <Options options={spec.bands} selected={value.band ? [value.band] : []} onPick={(v) => set("band", v)} dense />
        </div>
        <div className="flex flex-wrap items-center gap-x-2">
          <span className="text-xs text-muted w-10">Cup</span>
          <Options options={cups} selected={value.cup ? [value.cup] : []} onPick={(v) => set("cup", v)} dense />
          {!more && (
            <button type="button" onClick={() => setMore(true)} className="text-xs text-muted underline hover:text-ink">
              More
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Size choices in a row; `children` (an "Other" box) sits at the end of the same row. */
function Options({
  options,
  selected,
  onPick,
  dense = false,
  children,
}: {
  options: string[];
  selected: string[];
  onPick: (value: string) => void;
  dense?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className={`flex flex-wrap items-center gap-y-0.5 ${dense ? "text-sm gap-x-0" : "gap-x-1"}`}>
      {options.map((option) => (
        <button key={option} type="button" onClick={() => onPick(option)} aria-pressed={selected.includes(option)}>
          <HandCircle selected={selected.includes(option)}>{option}</HandCircle>
        </button>
      ))}
      {children && <span className="ml-2">{children}</span>}
    </div>
  );
}

/** A small "other" box for sizes beyond the listed ones (an unusual waist or inseam), checked against the range. */
function TypeIn({ label, range, onAdd }: { label: string; range: [number, number]; onAdd: (value: string) => void }) {
  const [text, setText] = useState("");
  const [bad, setBad] = useState(false);
  const add = () => {
    const n = Number(text);
    if (!text.trim()) return;
    if (!Number.isFinite(n) || n < range[0] || n > range[1] || (n * 2) % 1 !== 0) return setBad(true);
    onAdd(String(n));
    setText("");
    setBad(false);
  };
  return (
    <span className="flex items-baseline gap-2">
      <input
        className="input w-14 text-sm py-0"
        inputMode="decimal"
        placeholder="Other"
        aria-label={label}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setBad(false);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
      />
      {bad && <span className="text-xs text-muted">{range[0]}–{range[1]}, whole or half</span>}
    </span>
  );
}
