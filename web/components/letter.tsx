"use client";

import { useEffect, useRef, useState } from "react";

// Click the landing envelopes and a glassine sleeve opens (rectangular, like the landing photo): the straight flap
// folds back, then the shopper swipes up (trackpad, wheel or touch) to pull the landscape letter card out.
// The page behind is locked while open. Reduced-motion users get the letter already out.

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

type Stage = "closed" | "open" | "out"; // flap down, flap folded back (card inside), card pulled out

const PULL_OUT = 0.22; // drag the card up by this share of its height to take it out

export function Letter({ onClose }: { onClose: () => void }) {
  const [stage, setStage] = useState<Stage>("closed");
  const [drag, setDrag] = useState(0); // px the card is being pulled up (negative = up)
  const card = useRef<HTMLElement>(null);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStage("out");
      return;
    }
    const timer = setTimeout(() => setStage("open"), 300);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    const close = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", close);
    // Lock the page so a swipe only moves the letter.
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", close);
      document.body.style.overflow = overflow;
    };
  }, [onClose]);

  // Trackpad / mouse-wheel swipe up, anywhere on the screen: the card follows the swipe, and comes out once it's
  // pulled far enough; if the swipe stops short it settles back into the sleeve.
  const overlay = useRef<HTMLDivElement>(null);
  const stageRef = useRef(stage);
  stageRef.current = stage;
  useEffect(() => {
    const el = overlay.current;
    if (!el) return;
    let pulled = 0;
    let settle: ReturnType<typeof setTimeout> | undefined;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault(); // never scroll the page behind
      if (stageRef.current !== "open") return;
      const height = card.current?.offsetHeight ?? 300;
      pulled = Math.min(0, pulled - e.deltaY);
      if (-pulled > height * PULL_OUT) {
        pulled = 0;
        setDrag(0);
        setStage("out");
        return;
      }
      setDrag(Math.max(pulled, -height * 0.9));
      clearTimeout(settle);
      settle = setTimeout(() => {
        pulled = 0;
        setDrag(0);
      }, 180);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", onWheel);
      clearTimeout(settle);
    };
  }, []);

  // Touch: a finger swipe up on the card does the same. (Mouse click-and-drag isn't used.)
  function startPull(e: React.PointerEvent) {
    if (stage === "closed" || e.pointerType === "mouse") return;
    e.preventDefault();
    e.stopPropagation();
    const start = e.clientY;
    const height = card.current?.offsetHeight ?? 300;
    const target = e.currentTarget as HTMLElement;
    target.setPointerCapture(e.pointerId);
    let moved = 0;
    const onMove = (ev: PointerEvent) => {
      moved = Math.min(0, ev.clientY - start);
      setDrag(
        stage === "out"
          ? Math.max(moved, -height * 0.1)
          : Math.max(moved, -height * 0.9),
      );
    };
    const onUp = () => {
      target.removeEventListener("pointermove", onMove);
      target.removeEventListener("pointerup", onUp);
      target.removeEventListener("pointercancel", onUp);
      setDrag(0);
      // A pull past the threshold takes the card out; a short pull springs back.
      if (stage === "open" && -moved > height * PULL_OUT) setStage("out");
    };
    target.addEventListener("pointermove", onMove);
    target.addEventListener("pointerup", onUp);
    target.addEventListener("pointercancel", onUp);
  }

  const glass = {
    backgroundColor: PAPER,
    backgroundImage: GLASSINE,
    backdropFilter: "blur(1.5px)",
  };
  const resting = stage === "out" ? "-46%" : stage === "open" ? "-6%" : "0%";

  return (
    <div
      ref={overlay}
      role="dialog"
      aria-modal="true"
      aria-label="Why we built Niche"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center overflow-hidden overscroll-none bg-ink/90 backdrop-blur-sm px-4"
    >
      {/* Sleeve: back, letter card, front face, flap. Landscape, like the envelopes in the landing photo. */}
      <div
        onClick={(e) => e.stopPropagation()}
        className="relative w-[min(92vw,760px)] aspect-[16/10] translate-y-[18%] [perspective:1400px]"
      >
        <div
          className="absolute inset-0 shadow-[0_10px_40px_rgba(0,0,0,.5)]"
          style={glass}
        />

        {/* The card's lower edge stays inside the sleeve while it's pulled; once out it sits in front. */}
        <div
          className="absolute inset-0"
          style={{
            clipPath: stage === "out" ? "none" : "inset(-300% 0 1.5% 0)",
            zIndex: stage === "out" ? 40 : 10,
          }}
        >
          <article
            ref={card}
            onPointerDown={startPull}
            className={`absolute left-[3.5%] top-[7%] w-[93%] h-[88%] overflow-hidden bg-[#f8f5ee] text-ink px-[5%] py-[3.5%] shadow-[0_2px_14px_rgba(0,0,0,.25)] select-none touch-none ${drag ? "" : "transition-transform duration-700 ease-[cubic-bezier(.2,.8,.2,1)]"}`}
            style={{
              backgroundImage: LETTER_GRAIN,
              transform: `translateY(calc(${resting} + ${drag}px))`,
            }}
          >
            <p className="font-script text-xl sm:text-2xl mb-2">
              Why we built Niche
            </p>
            <div className="grid gap-1.5 font-serif text-[11px] leading-snug sm:text-[13.5px]">
              {PROBLEM.map((para) => (
                <p key={para.slice(0, 20)}>{para}</p>
              ))}
            </div>
            <p className="font-script text-base sm:text-lg mt-2 text-right">
              — the Niche team
            </p>
          </article>
        </div>

        {/* Front face: covers the sleeve below the flap line, in front of the card until it's out. */}
        <div
          className="absolute inset-0 z-20 border border-white/40"
          style={{ ...glass, clipPath: "inset(24% 0 0 0)" }}
        />

        {/* Straight flap with an adhesive strip, folding back from the top edge. */}
        <div
          className="absolute inset-x-0 top-0 h-[24%] origin-top border border-white/40 transition-transform duration-700 ease-in-out"
          style={{
            ...glass,
            transform: stage === "closed" ? "rotateX(0deg)" : "rotateX(180deg)",
            zIndex: stage === "closed" ? 30 : 5,
          }}
        >
          <div className="absolute inset-x-[6%] top-[30%] h-[22%] bg-white/30" />
        </div>

        <p
          className={`label absolute -bottom-10 left-1/2 -translate-x-1/2 whitespace-nowrap text-paper/70 transition-opacity ${stage === "open" ? "opacity-100" : "opacity-0"}`}
        >
          Swipe up to take out the letter ↑
        </p>
        <button
          onClick={onClose}
          className="label absolute -bottom-16 left-1/2 -translate-x-1/2 text-paper underline"
        >
          Close
        </button>
      </div>
    </div>
  );
}
