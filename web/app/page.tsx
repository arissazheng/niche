import Image from "next/image";
import Link from "next/link";

const CATEGORIES = ["Outerwear", "Knitwear", "Trousers", "Dresses", "Shoes", "Bags", "Vintage", "Handmade"];

export default function Home() {
  return (
    <div className="px-4">
      <p className="text-display text-center my-2">{CATEGORIES.join(", ")}</p>
      {/* Full-width band in the photo's own dark red, with the whole photo centred in it: nothing is cropped, and the
          photo's edges fade into the band so it reads as one image across the page. */}
      <section className="relative -mx-4 my-4 bg-[#1e070a] flex justify-center">
        <Image
          src="/niche-front.webp"
          alt="Niche"
          width={1080}
          height={1350}
          priority
          className="h-[70dvh] min-h-[380px] w-auto max-w-full object-contain [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]"
        />
        <Link
          href="/onboard"
          className="label absolute bottom-6 left-1/2 -translate-x-1/2 bg-paper text-ink px-6 py-3"
        >
          Find your niche
        </Link>
      </section>
      <section className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-6">
        {[
          ["1", "Tell us", "Answer a few questions out loud or by tapping."],
          ["2", "Show us", "Upload outfits and pieces you love. Click one to say what you like about it."],
          ["3", "Shop small", "We search independent labels, secondhand and major stores, and explain every match."],
        ].map(([n, title, body]) => (
          <div key={n} className="rule-t pt-1">
            <p className="text-display">{n}</p>
            <p className="text-display mt-6">{title}</p>
            <p className="text-sm mt-1 max-w-xs">{body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
