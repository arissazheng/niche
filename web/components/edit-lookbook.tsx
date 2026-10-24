import Link from "next/link";

/** Corner shortcut from the moodboard back to the lookbook, to add or remove photos. */
export function EditLookbookButton() {
  return (
    <Link
      href="/upload"
      aria-label="Edit lookbook: add or remove photos"
      className="group fixed bottom-6 right-6 z-30 flex items-center gap-2 rounded-full border border-ink bg-paper py-2 pl-2 pr-4 shadow-[0_2px_0_#000] hover:-translate-y-0.5 transition-transform"
    >
      <PencilAndEraser />
      <span className="label">Edit lookbook</span>
    </Link>
  );
}

function PencilAndEraser() {
  // Hand-drawn look: ink lines only, slightly wobbly, with hatching for shading.
  return (
    <svg
      viewBox="0 0 48 48"
      className="size-10"
      aria-hidden="true"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {/* eraser block lying down */}
      <g transform="rotate(-12 31 38)">
        <path d="M22.4 33.2 L39.6 32.8 Q40.3 33 40.2 34 L40 41.3 Q39.8 42.1 39 42 L22.6 42.2 Q21.8 42 21.9 41.2 L22 34 Q22 33.3 22.4 33.2 Z" fill="var(--color-paper, #fff)" />
        <path d="M28 33.1 L27.8 42.1" />
        <path d="M23.5 35.5 L26 33.5 M23.2 38.5 L27.3 35 M23.4 41.4 L27.5 37.8 M25.6 41.9 L27.5 40.3" strokeWidth="0.8" />
        <path d="M23 43.3 Q31 43.8 39.5 43" strokeWidth="0.8" />
      </g>
      {/* pencil, eraser end up */}
      <g transform="rotate(-45 24 22)">
        <path d="M8 17.2 L1.2 22 L8.1 26.9" fill="var(--color-paper, #fff)" />
        <path d="M1.2 22 L3.8 20.4 L3.9 23.6 Z" fill="currentColor" />
        <path d="M8 17 L31.8 17.3 L32 26.8 L8.1 27 Z" fill="var(--color-paper, #fff)" />
        <path d="M8.3 20.4 Q20 20.1 31.7 20.5 M8.2 23.7 Q20 23.9 31.9 23.5" strokeWidth="0.8" />
        <path d="M32 17.2 L36 17.1 L36.1 26.9 L32 26.8" fill="var(--color-paper, #fff)" />
        <path d="M33.3 17.4 L33.4 26.6 M34.7 17.3 L34.8 26.7" strokeWidth="0.8" />
        <path d="M36 17.1 L40.4 17.3 Q42.2 17.6 42.1 19.4 L42 24.8 Q41.9 26.7 40.2 26.8 L36.1 26.9" fill="var(--color-paper, #fff)" />
        <path d="M37.4 25.8 L40.6 18.6 M38.8 26 L41.4 20.3" strokeWidth="0.8" />
      </g>
    </svg>
  );
}
