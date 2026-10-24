"use client";

import { useEffect, useState } from "react";

// Click the landing envelopes and a glassine envelope opens: the flap folds back, a letter slides out and comes
// forward with the problem statement. Stages run on timers; reduced-motion users get the open letter at once.

const PROBLEM = [
  "Using AI to shop for clothes returns generic suggestions to shop from large brands (Urban Outfitters, American Eagle, etc.), but what about understanding your actual style preferences or supporting small businesses?",
  "Our solution is Niche, an AI platform that creates your taste profile using multimodal input. By uploading images of your outfits and clothes you like, we use multimodal clustering and object detection to infer style taste (colors, silhouettes, designers, etc.), with the option to use a voice agent to co-review and improve on the results of your taste profile.",
  "By steering away from corporate sponsorships with foundation model companies (i.e. Target & OpenAI), we aim to decrease financially-motivated biases towards recommending clothes that users might not actually want. Especially for individual sellers like small business owners or secondhand, niche marketplaces, whose products are not targeted by today’s AI agents, we want to help these entrepreneurs make their products visible.",
  "People are buying more products with agents, and small businesses shouldn’t be left behind.",
];

// Frosted glassine: translucent off-white with visible fibres and mottling (light and dark specks), so the letter
// shows through.
const GLASSINE =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='240' height='240'%3E%3Cfilter id='f'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .45 -.05'/%3E%3C/filter%3E%3Cfilter id='d'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='1.4' numOctaves='2' seed='4' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .35 0 0 0 0 .37 0 0 0 0 .36 0 0 0 .3 -.08'/%3E%3C/filter%3E%3Cfilter id='m'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.03' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .22 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23m)'/%3E%3Crect width='100%25' height='100%25' filter='url(%23f)'/%3E%3Crect width='100%25' height='100%25' filter='url(%23d)'/%3E%3C/svg%3E\")";
const PAPER = "rgba(232, 236, 234, 0.58)";

// Letter stock: warm off-white with fine grain, darker fibre flecks and soft mottling.
const LETTER_GRAIN =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='260' height='260'%3E%3Cfilter id='f'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .3 0 0 0 0 .27 0 0 0 0 .22 0 0 0 .32 -.04'/%3E%3C/filter%3E%3Cfilter id='m'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.025' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .4 0 0 0 0 .36 0 0 0 0 .3 0 0 0 .16 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23m)'/%3E%3Crect width='100%25' height='100%25' filter='url(%23f)'/%3E%3C/svg%3E\")";

type Stage = 0 | 1 | 2 | 3; // closed, flap open, letter out, letter forward

export function Letter({ onClose }: { onClose: () => void }) {
  const [stage, setStage] = useState<Stage>(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStage(3);
      return;
    }
    const timers = [
      setTimeout(() => setStage(1), 250),
      setTimeout(() => setStage(2), 950),
      setTimeout(() => setStage(3), 1900),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);

  useEffect(() => {
    const close = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);

  const glass = {
    backgroundColor: PAPER,
    backgroundImage: GLASSINE,
    backdropFilter: "blur(1.5px)",
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Why we built Niche"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/90 backdrop-blur-sm px-4 overflow-y-auto"
    >
      {/* Envelope: back panel, letter, front pocket, flap. Sized by width; the letter is taller than the envelope. */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-[min(92vw,640px)] aspect-[16/10] mt-[38vh] mb-12 [perspective:1400px]"
      >
        <div
          className="absolute inset-0 shadow-[0_8px_40px_rgba(0,0,0,.45)]"
          style={glass}
        />

        {/* The letter is taller than the envelope: its lower part stays hidden inside until it slides up. */}
        <div
          className="absolute inset-0"
          style={{
            clipPath: "inset(-300% 0 2% 0)",
            zIndex: stage >= 3 ? 40 : 10,
          }}
        >
          <article
            className="absolute left-[4%] w-[92%] bg-[#f8f5ee] text-ink px-[6%] py-[5%] shadow-[0_2px_14px_rgba(0,0,0,.25)] transition-transform duration-[900ms] ease-[cubic-bezier(.2,.8,.2,1)]"
            style={{
              top: "6%",
              backgroundImage: LETTER_GRAIN,
              transform: stage >= 2 ? "translateY(-78%)" : "translateY(0)",
            }}
          >
            <p className="font-script text-2xl mb-3">Why we built Niche</p>
            <div className="grid gap-2 font-serif text-[15px] leading-snug sm:text-base">
              {PROBLEM.map((para) => (
                <p key={para.slice(0, 20)}>{para}</p>
              ))}
            </div>
            <p className="font-script text-xl mt-4 text-right">
              — the Niche team
            </p>
          </article>
        </div>

        {/* Front pocket: the envelope face with a V notch, in front of the letter until the letter comes forward. */}
        <div
          className="absolute inset-0 z-20 border border-white/40"
          style={{
            ...glass,
            clipPath: "polygon(0 0, 50% 46%, 100% 0, 100% 100%, 0 100%)",
          }}
        />

        {/* Flap: folds back from the top edge; once open it sits behind the letter. */}
        <div
          className="absolute inset-x-0 top-0 h-[56%] origin-top transition-transform duration-700 ease-in-out"
          style={{
            ...glass,
            clipPath: "polygon(0 0, 100% 0, 50% 100%)",
            transform: stage >= 1 ? "rotateX(180deg)" : "rotateX(0deg)",
            zIndex: stage >= 1 ? 5 : 30,
          }}
        />

        <button
          onClick={onClose}
          className="label absolute -bottom-10 left-1/2 -translate-x-1/2 text-paper underline"
          autoFocus
        >
          Close
        </button>
      </div>
    </div>
  );
}
