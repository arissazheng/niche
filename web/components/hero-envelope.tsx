"use client";

import Image from "next/image";
import { useState } from "react";
import { Letter } from "./letter";

/** The landing envelopes; clicking them opens the letter with the problem statement. */
export function HeroEnvelope() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open the letter: why we built Niche"
        className="group relative cursor-pointer"
      >
        <Image
          src="/niche-front-envelopes.webp"
          alt="Niche"
          width={802}
          height={708}
          priority
          className="h-[60dvh] min-h-[320px] w-auto max-w-[92vw] object-contain transition-transform duration-500 group-hover:-translate-y-1 group-hover:rotate-[-0.6deg]"
        />
        <span className="label absolute -bottom-7 left-1/2 -translate-x-1/2 whitespace-nowrap text-paper/70 group-hover:text-paper">
          Open the letter
        </span>
      </button>
      {open && <Letter onClose={() => setOpen(false)} />}
    </>
  );
}
