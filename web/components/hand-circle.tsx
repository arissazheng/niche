/** Hand-drawn circle around a selected option (design deck, "Profile Setup + Voice"). */
export function HandCircle({ selected, children }: { selected: boolean; children: React.ReactNode }) {
  return (
    <span className="relative inline-block px-2 py-1">
      {children}
      {selected && (
        <svg
          aria-hidden
          viewBox="0 0 100 50"
          preserveAspectRatio="none"
          className="pointer-events-none absolute -inset-1 h-[calc(100%+0.5rem)] w-[calc(100%+0.5rem)]"
        >
          <path
            d="M8 27 C 6 10, 40 3, 62 5 C 88 7, 97 18, 93 31 C 88 45, 45 48, 22 43 C 6 39, 3 26, 15 15"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      )}
    </span>
  );
}
