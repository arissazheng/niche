"use client";

import { useEffect, useRef, useState } from "react";
import { useSpacetimeDB, useTable } from "spacetimedb/react";
import { tables, type DbConnection } from "@/lib/spacetime";
import type { ProfileView, StyleCluster, TasteImage } from "@/lib/types";

// One open, ring-bound spread that fills the screen. Every cluster is a loose, overlapping collage
// (prints, an embossed heading slip, a vellum note, color dots). Every piece can be
// dragged. Positions and cursors live in SpacetimeDB, so everyone with the board link sees moves live.

type PieceKind = "image" | "slip" | "note" | "dots" | "title";

interface Piece {
  id: string;
  kind: PieceKind;
  left: number; // % of spread width
  top: number; // % of spread height
  width: number; // % of spread width
  rotate: number;
  z: number;
  image?: TasteImage;
  cluster?: StyleCluster;
  index?: number;
  text?: string;
  colors?: string[];
  torn?: { paper: string; ink: string }; // clip-path polygons: ripped paper edge, and where the printed layer stops
}

interface Moved {
  dx: number;
  dy: number;
  z: number;
}

const GUTTER = 1.2; // % of spread width between the two pages
const PAPER_INSET_X = 1; // % of spread width between the screen edge and the paper
const PAPER_INSET_Y = 1.5; // % of spread height

const CLICK_SLOP_PX = 4; // less movement than this between press and release counts as a click
const SEND_EVERY_MS = 60; // live drag updates; the drop always sends the final position
const CURSOR_EVERY_MS = 80;
const CURSOR_STALE_MS = 30_000;

export function Binder({
  view,
  viewerName,
  onOpenImage,
  readOnly = false,
}: {
  view: ProfileView;
  viewerName: string;
  onOpenImage?: (image: TasteImage) => void;
  readOnly?: boolean; // a friend's view through a share link: look, don't rearrange
}) {
  const spreadRef = useRef<HTMLDivElement>(null);
  const aspect = useAspect(spreadRef);
  const shapes = useShapes(view.images);
  const pieces = layout(view, shapes, aspect, readOnly);
  // A rebuilt profile has different clusters, so each version gets a fresh board.
  const boardId = `${view.board_id ?? view.profile.id}:v${view.profile.version}`;

  const { isActive, identity, getConnection } = useSpacetimeDB();
  const conn = getConnection() as DbConnection | null;
  const [rows] = useTable(tables.boardPiece.where((r) => r.boardId.eq(boardId)));
  const [cursorRows] = useTable(tables.boardCursor.where((r) => r.boardId.eq(boardId)));

  const shared: Record<string, Moved> = {};
  for (const row of rows) shared[row.pieceId] = { dx: row.dx, dy: row.dy, z: row.z };
  // Your own drag wins while it's in flight; `pending` holds dropped positions until the server echoes them
  // (and keeps the board usable on its own if the live connection is down).
  const [dragging, setDragging] = useState<{ id: string; moved: Moved } | null>(null);
  const [pending, setPending] = useState<Record<string, Moved>>({});
  const position = (id: string) => (dragging?.id === id ? dragging.moved : pending[id] ?? shared[id]);

  useEffect(() => {
    setPending((current) => {
      const left = Object.entries(current).filter(([id, m]) => {
        const echo = rows.find((r) => r.pieceId === id);
        return !(echo && echo.dx === m.dx && echo.dy === m.dy && echo.z === m.z);
      });
      return left.length === Object.keys(current).length ? current : Object.fromEntries(left);
    });
  }, [rows]);

  const send = (pieceId: string, m: Moved) => {
    if (!conn || !isActive) return;
    conn.reducers.movePiece({ boardId, pieceId, dx: m.dx, dy: m.dy, z: m.z }).catch(() => {});
  };

  function startDrag(e: React.PointerEvent, piece: Piece) {
    if (readOnly) return;
    const spread = spreadRef.current;
    if (!spread || e.button !== 0) return;
    e.preventDefault();
    const rect = spread.getBoundingClientRect();
    const start = { x: e.clientX, y: e.clientY };
    const base = position(piece.id) ?? { dx: 0, dy: 0, z: piece.z };
    const highest = Math.max(100, ...rows.map((r) => r.z), ...Object.values(pending).map((m) => m.z));
    const z = highest + 1; // picking something up puts it on top of the pile, for everyone
    const target = e.currentTarget as HTMLElement;
    target.setPointerCapture(e.pointerId);

    let latest = { ...base, z };
    let travelled = 0;
    let lastSent = 0;
    const onMove = (ev: PointerEvent) => {
      travelled = Math.max(travelled, Math.hypot(ev.clientX - start.x, ev.clientY - start.y));
      latest = {
        dx: base.dx + ((ev.clientX - start.x) / rect.width) * 100,
        dy: base.dy + ((ev.clientY - start.y) / rect.height) * 100,
        z,
      };
      setDragging({ id: piece.id, moved: latest });
      if (ev.timeStamp - lastSent > SEND_EVERY_MS) {
        lastSent = ev.timeStamp;
        send(piece.id, latest);
      }
    };
    const onUp = () => {
      target.removeEventListener("pointermove", onMove);
      target.removeEventListener("pointerup", onUp);
      target.removeEventListener("pointercancel", onUp);
      if (travelled < CLICK_SLOP_PX && piece.kind === "image" && piece.image) onOpenImage?.(piece.image);
      setPending((p) => ({ ...p, [piece.id]: latest }));
      setDragging(null);
      send(piece.id, latest);
    };
    target.addEventListener("pointermove", onMove);
    target.addEventListener("pointerup", onUp);
    target.addEventListener("pointercancel", onUp);
    setDragging({ id: piece.id, moved: latest });
  }

  function reset() {
    setPending({});
    if (conn && isActive) conn.reducers.resetBoard({ boardId }).catch(() => {});
  }

  // Cursor presence: where you are on the spread, shared with everyone on this board.
  const lastCursor = useRef(0);
  const myColor = identity ? cursorColor(identity.toHexString()) : "#000";
  function trackCursor(e: React.PointerEvent) {
    const spread = spreadRef.current;
    if (!spread || !conn || !isActive || e.timeStamp - lastCursor.current < CURSOR_EVERY_MS) return;
    lastCursor.current = e.timeStamp;
    const rect = spread.getBoundingClientRect();
    conn.reducers
      .moveCursor({
        boardId,
        name: viewerName,
        color: myColor,
        x: ((e.clientX - rect.left) / rect.width) * 100,
        y: ((e.clientY - rect.top) / rect.height) * 100,
      })
      .catch(() => {});
  }
  function leave() {
    if (conn && isActive) conn.reducers.leaveBoard({ boardId }).catch(() => {});
  }
  const leaveRef = useRef(leave);
  leaveRef.current = leave;
  useEffect(() => () => leaveRef.current(), [boardId]);

  const me = identity?.toHexString();
  const now = Date.now();
  const others = cursorRows.filter(
    (c) =>
      c.viewer.toHexString() !== me &&
      now - Number(c.updatedAt.microsSinceUnixEpoch / BigInt(1000)) < CURSOR_STALE_MS,
  );

  return (
    // isolate: piece z-indexes (which grow as things are picked up) stay inside the book, under page overlays.
    <section className="relative isolate bg-ink overflow-x-auto">
      <div
        ref={spreadRef}
        onPointerMove={trackCursor}
        onPointerLeave={leave}
        className="relative h-[calc(100dvh-3.5rem)] min-h-[560px] w-full min-w-[960px] overflow-hidden select-none"
      >
        <Paper side="left" />
        <Paper side="right" />
        {/* Everything on the pages is trimmed at the paper's outer edge, matching the Paper insets below. */}
        <div className="absolute inset-0" style={{ clipPath: `inset(${PAPER_INSET_Y}% ${PAPER_INSET_X}%)` }}>
          {pieces.map((piece) => {
            const m = position(piece.id);
            return (
              <div
                key={piece.id}
                onPointerDown={(e) => startDrag(e, piece)}
                className={`absolute touch-none ${readOnly ? "" : "cursor-grab active:cursor-grabbing"}`}
                style={{
                  left: `${piece.left + (m?.dx ?? 0)}%`,
                  top: `${piece.top + (m?.dy ?? 0)}%`,
                  width: `${piece.width}%`,
                  rotate: `${piece.rotate}deg`,
                  zIndex: m?.z ?? piece.z,
                }}
              >
                <PieceBody piece={piece} />
              </div>
            );
          })}
        </div>
        <Rings />
        {others.map((c) => (
          <Cursor key={c.key} x={c.x} y={c.y} name={c.name} color={c.color} />
        ))}
      </div>
      {!readOnly && (
        <div className="absolute bottom-3 right-4 z-[999] flex gap-4 bg-ink text-paper px-3 py-1.5">
          <span className="label opacity-60">
            {others.length > 0 ? `${others.length + 1} people here · ` : ""}Drag to rearrange · click a photo to edit its notes
          </span>
          <button onClick={reset} className="label underline">Reset layout</button>
        </div>
      )}
    </section>
  );
}

/** The spread's width / height, so prints keep their proportions in percentage coordinates. */
function useAspect(ref: React.RefObject<HTMLDivElement | null>) {
  const [aspect, setAspect] = useState(1.7);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => el.clientHeight && setAspect(el.clientWidth / el.clientHeight);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref]);
  return aspect;
}

/** Each photo's real width / height, loaded once per photo (links are re-signed hourly, so keyed by image id). */
function useShapes(images: TasteImage[]) {
  const [shapes, setShapes] = useState<Shapes>({});
  useEffect(() => {
    let live = true;
    for (const image of images) {
      if (shapes[image.id]) continue;
      const probe = new Image();
      probe.onload = () => {
        if (live && probe.naturalHeight) setShapes((s) => ({ ...s, [image.id]: probe.naturalWidth / probe.naturalHeight }));
      };
      probe.src = image.url;
    }
    return () => {
      live = false;
    };
  }, [images]); // eslint-disable-line react-hooks/exhaustive-deps -- shapes only grows; re-probing is wasted work
  return shapes;
}

function Cursor({ x, y, name, color }: { x: number; y: number; name: string; color: string }) {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute z-[950] transition-[left,top] duration-75 ease-linear"
      style={{ left: `${x}%`, top: `${y}%` }}
    >
      <svg viewBox="0 0 16 20" className="w-4 drop-shadow-sm">
        <path d="M1 1 L1 16 L5 12 L8 19 L11 18 L8 11 L14 11 Z" fill={color} stroke="#fff" strokeWidth="1.2" />
      </svg>
      <span className="font-hand text-lg leading-none ml-3 px-1 bg-paper/80" style={{ color }}>
        {name}
      </span>
    </div>
  );
}

const CURSOR_COLORS = ["#b5452a", "#2f5d8a", "#3d7a4a", "#8a3f7a", "#a8741a", "#1f6f6f"];

function cursorColor(identityHex: string) {
  let h = 0;
  for (const ch of identityHex) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return CURSOR_COLORS[h % CURSOR_COLORS.length];
}

function PieceBody({ piece }: { piece: Piece }) {
  switch (piece.kind) {
    case "image":
      if (piece.torn) {
        // clip-path removes box-shadow, so the shadow comes from a drop-shadow filter on the wrapper.
        return (
          <figure style={{ filter: "drop-shadow(0 1px 2.5px rgba(0,0,0,.28))" }}>
            {/* The paper layer shows as an uneven white fringe where the printed layer peeled back. */}
            <div className="bg-[#fefdfb]" style={{ clipPath: `polygon(${piece.torn.paper})`, backgroundImage: PAPER_TEXTURE }}>
              {/* eslint-disable-next-line @next/next/no-img-element -- user uploads served by the API */}
              <img
                src={piece.image!.url}
                alt=""
                draggable={false}
                className="block w-full"
                style={{ clipPath: `polygon(${piece.torn.ink})` }}
              />
            </div>
          </figure>
        );
      }
      return (
        <figure className="relative shadow-[0_1px_6px_rgba(0,0,0,.22)]">
          {/* eslint-disable-next-line @next/next/no-img-element -- user uploads served by the API */}
          <img src={piece.image!.url} alt="" draggable={false} className="block w-full" />
          {piece.text === "tape" && <Tape />}
          {piece.text === "clip" && <BinderClip />}
        </figure>
      );
    case "slip":
      return (
        // Translucent vellum: the pile shows through, with paper grain and embossed corner flourishes.
        <div
          className="relative bg-[#f8f5ee]/[.86] backdrop-blur-[2px] px-[2.6vw] py-[1.5vw] shadow-[0_1px_3px_rgba(0,0,0,.14),inset_0_0_0_1px_rgba(255,255,255,.45)]"
          style={{ backgroundImage: SLIP_TEXTURE }}
        >
          <Emboss />
          <p className="relative font-script text-[1.75vw] leading-[1.25] text-[#1d1c1a]">{piece.cluster!.name}</p>
        </div>
      );
    case "note":
      return (
        <div className="relative bg-[#f7f6f2]/75 backdrop-blur-[3px] px-[0.8vw] py-[0.7vw] shadow-[0_1px_2px_rgba(0,0,0,.1)]">
          <Paperclip />
          <p className="font-serif italic text-[0.95vw] leading-[1.25]">{piece.text}</p>
        </div>
      );
    case "dots":
      return (
        <div className="flex gap-[0.5vw]">
          {piece.colors!.map((c) => (
            <span key={c} className="size-[1.25vw] rounded-full shadow-[inset_0_0_0_1px_rgba(0,0,0,.08)]" style={{ background: c }} title={c} />
          ))}
        </div>
      );
    case "title":
      return (
        <p className="font-script text-[2.6vw] leading-none">{piece.text}</p>
      );
  }
}

/** Width / height of a photo; 3:4 until the photo has loaded and its real shape is known. */
type Shapes = Record<string, number>;
const DEFAULT_SHAPE = 3 / 4;
const PAGE_TOP = 11; // % of spread height: below the title
const PAGE_BOTTOM = 96.5; // % of spread height: the paper ends at 98.5
const OVERLAP = 1.12; // prints are a little larger than their slot, so neighbours overlap without hiding each other

interface Zone {
  left: number;
  top: number;
  width: number;
  height: number;
  page: { left: number; right: number };
}

/**
 * Balances clusters across both pages by photo count, gives each cluster a zone sized to its photos, then lays its
 * prints out on a loose grid sized to the zone, so every print stays mostly visible and inside the page.
 * `aspect` is the spread's width / height, used to keep each print's real proportions.
 */
function layout(view: ProfileView, shapes: Shapes, aspect: number, readOnly = false): Piece[] {
  const byId = new Map(view.images.map((x) => [x.id, x]));
  const placed = new Set<string>();
  const clusters = view.profile.clusters.map((cluster) => {
    const images = cluster.image_ids.map((id) => byId.get(id)).filter((x): x is TasteImage => !!x);
    images.forEach((x) => placed.add(x.id));
    return { cluster, images };
  });
  const loose = view.images.filter((x) => !placed.has(x.id));
  if (loose.length) {
    clusters.push({
      cluster: { name: "Loose pages", description: "", image_ids: [], colors: [], silhouettes: [], patterns: [] },
      images: loose,
    });
  }

  const name = view.profile.onboarding.name.trim();
  const pieces: Piece[] = [
    { id: "title", kind: "title", left: 3, top: 3, width: 20, rotate: -2, z: 60, text: name ? `${name}'s taste` : readOnly ? "Their taste" : "My taste" },
  ];
  const zoneFor = zones(clusters.map((c) => c.images.length));

  clusters.forEach(({ cluster, images }, i) => {
    const zone = zoneFor[i];
    const rand = seeded(cluster.name + i);
    const n = Math.max(images.length, 1);
    // Columns chosen so each slot is roughly portrait, like the prints.
    const zoneShape = (zone.width * aspect) / zone.height;
    const cols = Math.min(n, Math.max(1, Math.round(Math.sqrt((n * zoneShape) / DEFAULT_SHAPE))));
    const rows = Math.ceil(n / cols);
    const cellW = zone.width / cols;
    const cellH = zone.height / rows;
    const clamp = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), Math.max(lo, hi));

    images.forEach((image, k) => {
      const row = Math.floor(k / cols);
      const inRow = row === rows - 1 ? n - row * cols : cols;
      const col = k % cols;
      const shape = shapes[image.id] ?? DEFAULT_SHAPE;
      // Fit the print to its slot (by width or by height, whichever is tighter), then enlarge slightly.
      const width = Math.min(cellW, (cellH / aspect) * shape) * OVERLAP;
      const height = (width * aspect) / shape;
      const rowOffset = ((cols - inRow) * cellW) / 2; // centre a short last row
      const left = zone.left + rowOffset + col * cellW + (cellW - width) / 2 + (rand() - 0.5) * cellW * 0.12;
      const top = zone.top + row * cellH + (cellH - height) / 2 + (rand() - 0.5) * cellH * 0.12;
      pieces.push({
        id: image.id,
        kind: "image",
        left: clamp(left, zone.page.left, zone.page.right - width),
        top: clamp(top, PAGE_TOP - 2, PAGE_BOTTOM - height),
        width,
        rotate: (rand() - 0.5) * 5,
        z: 10 + row * 4 + Math.floor(rand() * 4),
        image,
        ...decoration(rand, image.id),
      });
    });

    // Heading slip sits on top of the pile near the zone's upper-left; the note overlaps the lower-right.
    const slipWidth = Math.min(zone.width * 0.48, 19);
    pieces.push({
      id: `slip:${i}`,
      kind: "slip",
      left: clamp(zone.left + zone.width * (0.02 + rand() * 0.08), zone.page.left, zone.page.right - slipWidth),
      top: zone.top + zone.height * (0.02 + rand() * 0.06),
      width: slipWidth,
      rotate: (rand() - 0.5) * 5,
      z: 70,
      cluster,
      index: i,
    });
    if (cluster.description) {
      const noteWidth = Math.min(zone.width * 0.4, 15);
      pieces.push({
        id: `note:${i}`,
        kind: "note",
        left: clamp(zone.left + zone.width * (0.58 + rand() * 0.06), zone.page.left, zone.page.right - noteWidth),
        top: Math.min(zone.top + zone.height * (0.6 + rand() * 0.1), PAGE_BOTTOM - 18),
        width: noteWidth,
        rotate: (rand() - 0.5) * 6,
        z: 75,
        text: cardText(cluster.description),
      });
    }
    const colors = [...new Set(images.flatMap((x) => x.palette.slice(0, 2)))].slice(0, 5);
    if (colors.length) {
      pieces.push({
        id: `dots:${i}`,
        kind: "dots",
        left: zone.left + zone.width * 0.03,
        top: Math.min(zone.top + zone.height - 3, PAGE_BOTTOM - 2.5),
        width: 9,
        rotate: 0,
        z: 65,
        colors,
      });
    }
  });
  return pieces;
}

/**
 * One zone per cluster. Clusters go to whichever page has fewer photos so far (biggest first), so both pages fill
 * evenly. A page with three or more clusters splits into two columns the same way; within a column, clusters stack
 * with heights in proportion to their photo counts.
 */
function zones(counts: number[]): Zone[] {
  const pageWidth = (100 - GUTTER) / 2;
  const weight = (n: number) => Math.max(n, 1) + 1;
  const spread = (indices: number[], parts: number) => {
    const bins: number[][] = Array.from({ length: parts }, () => []);
    const load = new Array(parts).fill(0);
    for (const i of [...indices].sort((a, b) => counts[b] - counts[a])) {
      const lightest = load.indexOf(Math.min(...load));
      bins[lightest].push(i);
      load[lightest] += weight(counts[i]);
    }
    return bins.map((bin) => bin.sort((a, b) => a - b)); // keep the profile's order within a page
  };

  const out: Zone[] = [];
  spread(counts.map((_, i) => i), counts.length > 1 ? 2 : 1).forEach((onPage, page) => {
    const x0 = page * (pageWidth + GUTTER) + 3;
    const w = pageWidth - 6;
    const bounds = { left: x0 - 1.5, right: x0 + w + 1.5 };
    const columns = spread(onPage, onPage.length >= 3 ? 2 : 1);
    columns.forEach((column, c) => {
      const total = column.reduce((sum, i) => sum + weight(counts[i]), 0);
      let y = PAGE_TOP;
      for (const i of column) {
        const height = ((PAGE_BOTTOM - PAGE_TOP) * weight(counts[i])) / total;
        out[i] = { left: x0 + (c * w) / columns.length, top: y, width: w / columns.length, height, page: bounds };
        y += height;
      }
    });
  });
  return out;
}

/**
 * The note card's paragraph. New builds write at most 35 words; older, longer descriptions keep whole sentences up to
 * the card's length, or end at the last full phrase (a comma break) with a period, never a clipped "…".
 */
function cardText(description: string, max = 220) {
  const text = description.trim();
  if (text.length <= max) return text;
  const sentences = text.match(/[^.!?]+[.!?]+/g) ?? [];
  let kept = "";
  for (const sentence of sentences) {
    if ((kept + sentence).length > max) break;
    kept += sentence;
  }
  if (kept) return kept.trim();
  const cut = text.slice(0, max);
  const phrase = cut.slice(0, Math.max(cut.lastIndexOf(","), cut.lastIndexOf(";")));
  return `${(phrase || cut.replace(/\s+\S*$/, "")).replace(/[:,;\s]+$/, "")}.`;
}

/** About a third of prints are torn out of a magazine; the rest get tape, a binder clip or nothing. */
function decoration(rand: () => number, id: string): Pick<Piece, "text" | "torn"> {
  const roll = rand();
  if (roll < 0.35) {
    const tear = seeded(`torn:${id}`);
    // Real rips rarely go all the way round: tear one or two sides, keep the rest as clean cuts.
    const sides = (["top", "right", "bottom", "left"] as const).slice().sort(() => tear() - 0.5);
    return { torn: tornEdge(tear, new Set(sides.slice(0, tear() < 0.55 ? 1 : 2))) };
  }
  if (roll < 0.6) return { text: "tape" };
  if (roll < 0.7) return { text: "clip" };
  return {};
}

type Side = "top" | "right" | "bottom" | "left";

/**
 * Clip-path polygons (percent coords) for a print ripped along the given sides. `paper` follows the rip;
 * `ink` follows it too but is pulled inward by a patchy amount, exposing white paper core in places.
 */
function tornEdge(rand: () => number, torn: Set<Side>, depth = 4, fringe = 1.6) {
  const steps = 64;
  let wander = 0;
  let peel = 0;
  const point = (side: Side): [number, number] => {
    if (!torn.has(side)) return [0, 0];
    wander = Math.max(-1, Math.min(1, wander * 0.8 + (rand() - 0.5) * 0.8));
    const nick = rand() < 0.08 ? depth * 0.6 : 0;
    const rip = depth * (0.4 + 0.35 * wander) + rand() * depth * 0.5 + nick;
    // Slowly varying peel, clipped at zero so the white comes and goes along the edge.
    peel = Math.max(-1, Math.min(1, peel * 0.85 + (rand() - 0.5) * 0.7));
    const white = Math.max(0, peel + 0.25) * fringe + rand() * fringe * 0.25;
    return [rip, rip + white];
  };
  const paper: string[] = [];
  const ink: string[] = [];
  const add = (side: Side, at: (inset: number) => string) => {
    const [rip, inner] = point(side);
    paper.push(at(rip));
    ink.push(at(inner));
  };
  for (let i = 0; i < steps; i++) add("top", (d) => `${(i / steps) * 100}% ${d}%`);
  for (let i = 0; i < steps; i++) add("right", (d) => `${100 - d}% ${(i / steps) * 100}%`);
  for (let i = 0; i < steps; i++) add("bottom", (d) => `${100 - (i / steps) * 100}% ${100 - d}%`);
  for (let i = 0; i < steps; i++) add("left", (d) => `${d}% ${100 - (i / steps) * 100}%`);
  return { paper: paper.join(", "), ink: ink.join(", ") };
}

// Page stock: visible fine grain plus broad, uneven mottling.
const PAPER_TEXTURE =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='260'%3E%3Cfilter id='f'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.8' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .25 0 0 0 0 .22 0 0 0 0 .18 0 0 0 .22 0'/%3E%3C/filter%3E%3Cfilter id='m'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.02' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .3 0 0 0 0 .27 0 0 0 0 .22 0 0 0 .14 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23m)'/%3E%3Crect width='100%25' height='100%25' filter='url(%23f)'/%3E%3C/svg%3E\")";

// Heavier grain for the header slips: fine fibres plus soft mottling, like handmade card stock.
const SLIP_TEXTURE =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='f'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .25 0 0 0 0 .22 0 0 0 0 .18 0 0 0 .4 0'/%3E%3C/filter%3E%3Cfilter id='m'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.035' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .3 0 0 0 0 .27 0 0 0 0 .22 0 0 0 .18 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23m)'/%3E%3Crect width='100%25' height='100%25' filter='url(%23f)'/%3E%3C/svg%3E\")";

function Paper({ side }: { side: "left" | "right" }) {
  const spine =
    side === "left"
      ? "linear-gradient(to left, rgba(0,0,0,.16), rgba(0,0,0,0) 5%)"
      : "linear-gradient(to right, rgba(0,0,0,.16), rgba(0,0,0,0) 5%)";
  return (
    <div
      aria-hidden
      className="absolute bg-[#f3f1eb]"
      style={{
        top: `${PAPER_INSET_Y}%`,
        bottom: `${PAPER_INSET_Y}%`,
        left: side === "left" ? `${PAPER_INSET_X}%` : `${50 + GUTTER / 2}%`,
        right: side === "left" ? `${50 + GUTTER / 2}%` : `${PAPER_INSET_X}%`,
        backgroundImage: `${spine}, ${PAPER_TEXTURE}`,
      }}
    />
  );
}

function Rings() {
  return (
    <div aria-hidden className="pointer-events-none absolute inset-y-0 left-1/2 -translate-x-1/2 w-[4.2%] z-[900]">
      {[10, 28, 72, 90].map((top) => (
        <svg key={top} viewBox="0 0 60 30" className="absolute w-full -translate-y-1/2" style={{ top: `${top}%` }}>
          <defs>
            <linearGradient id={`metal-${top}`} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#f4f4f4" />
              <stop offset=".45" stopColor="#8d8d8f" />
              <stop offset=".7" stopColor="#d9d9db" />
              <stop offset="1" stopColor="#5e5e60" />
            </linearGradient>
          </defs>
          <circle cx="9" cy="22" r="4" fill="#1b1b1b" />
          <circle cx="51" cy="22" r="4" fill="#1b1b1b" />
          <path d="M9 22 C 9 2, 51 2, 51 22" fill="none" stroke={`url(#metal-${top})`} strokeWidth="4" strokeLinecap="round" />
          <path d="M12 17 C 16 7, 30 5, 40 8" fill="none" stroke="#fff" strokeOpacity=".7" strokeWidth="1" strokeLinecap="round" />
        </svg>
      ))}
    </div>
  );
}

/** Raised four-petal flourishes with dotted edges in each corner, like blind-embossed card stock. */
function Emboss() {
  const corners = [
    "left-[3%] top-[6%]",
    "right-[3%] top-[6%] -scale-x-100",
    "left-[3%] bottom-[6%] -scale-y-100",
    "right-[3%] bottom-[6%] -scale-100",
  ];
  return (
    <>
      {corners.map((place) => (
        <svg key={place} viewBox="0 0 40 40" className={`pointer-events-none absolute w-[2.3vw] ${place}`} aria-hidden>
          <g fill="#fbfaf6" style={{ filter: "drop-shadow(0.4px 0.8px 0.3px rgba(0,0,0,.35)) drop-shadow(-0.4px -0.5px 0 #fff)" }}>
            <path d="M12 4 C 10 9, 10 9, 12 12 C 14 9, 14 9, 12 4 Z M12 20 C 10 15, 10 15, 12 12 C 14 15, 14 15, 12 20 Z M4 12 C 9 10, 9 10, 12 12 C 9 14, 9 14, 4 12 Z M20 12 C 15 10, 15 10, 12 12 C 15 14, 15 14, 20 12 Z" />
            <circle cx="26" cy="12" r="1.4" />
            <circle cx="33" cy="12" r="1.4" />
            <circle cx="12" cy="26" r="1.4" />
            <circle cx="12" cy="33" r="1.4" />
          </g>
        </svg>
      ))}
    </>
  );
}

function Tape() {
  return (
    <span
      aria-hidden
      className="absolute left-1/2 -top-[0.6vw] h-[1.2vw] w-[42%] -translate-x-1/2 -rotate-3 bg-[#e9dfc7]/80 shadow-[0_1px_1px_rgba(0,0,0,.08)]"
    />
  );
}

function BinderClip() {
  return (
    <svg viewBox="0 0 40 34" className="absolute left-1/2 -top-[1.4vw] w-[2.4vw] -translate-x-1/2" aria-hidden>
      <path d="M12 16 C 8 2, 18 0, 20 8 C 22 0, 32 2, 28 16" fill="none" stroke="#b9b9bb" strokeWidth="1.6" />
      <rect x="5" y="15" width="30" height="14" rx="1.5" fill="#2a2a2c" />
      <rect x="5" y="15" width="30" height="3" fill="#4a4a4d" />
    </svg>
  );
}

function Paperclip() {
  return (
    <svg viewBox="0 0 16 40" className="absolute -top-[1vw] left-[8%] w-[0.9vw]" aria-hidden>
      <path d="M11 14 V 31 a 4 4 0 0 1 -8 0 V 8 a 5.5 5.5 0 0 1 11 0 V 30" fill="none" stroke="#9a9a9c" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function seeded(seed: string) {
  let h = 2166136261;
  for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return ((h ^= h >>> 16) >>> 0) / 4294967296;
  };
}
