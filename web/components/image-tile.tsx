"use client";

import type { TasteImage } from "@/lib/types";

/** Grey plinth tile with index number. Clicking opens the detail note. */
export function ImageTile({ image, index, onOpen }: { image: TasteImage; index: number; onOpen: () => void }) {
  return (
    <figure>
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Add details to image ${index}`}
        className="bg-plinth aspect-[3/4] w-full flex items-center justify-center overflow-hidden cursor-pointer"
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- user uploads served by the API */}
        <img src={image.url} alt="" draggable={false} className="max-h-full max-w-full object-contain" />
      </button>
      <figcaption className="flex items-start justify-between mt-1 gap-2">
        <span className="text-display">{index}</span>
        <span className="flex gap-0.5 pt-1" aria-label="Measured palette">
          {image.palette.slice(0, 5).map((c) => (
            <span key={c} className="size-3" style={{ background: c }} title={c} />
          ))}
        </span>
      </figcaption>
      {image.note && <p className="text-xs mt-1 line-clamp-2">“{image.note}”</p>}
    </figure>
  );
}
