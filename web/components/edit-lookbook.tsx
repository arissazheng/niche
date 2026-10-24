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
  return (
    <svg viewBox="0 0 48 48" className="size-10" aria-hidden="true">
      {/* eraser block lying down */}
      <g transform="rotate(-12 31 38)">
        <rect x="22" y="33" width="18" height="9" rx="2" fill="#f6b3c4" stroke="#000" strokeWidth="1.5" />
        <rect x="22" y="33" width="6" height="9" rx="1" fill="#9ec5f0" stroke="#000" strokeWidth="1.5" />
      </g>
      {/* pencil, eraser end up */}
      <g transform="rotate(-45 24 22)">
        <polygon points="8,17 1,22 8,27" fill="#f3e3c3" stroke="#000" strokeWidth="1.5" strokeLinejoin="round" />
        <polygon points="1,22 4,20.3 4,23.7" fill="#000" />
        <rect x="8" y="17" width="24" height="10" fill="#ffd45c" stroke="#000" strokeWidth="1.5" />
        <rect x="32" y="17" width="4" height="10" fill="#c9c9cf" stroke="#000" strokeWidth="1.5" />
        <rect x="36" y="17" width="6" height="10" rx="2" fill="#f6b3c4" stroke="#000" strokeWidth="1.5" />
      </g>
    </svg>
  );
}
