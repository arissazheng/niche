"use client";

import Link, { useLinkStatus } from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { APP_NAME, FRIEND_EVENT, clearFriendView, getFriendView, startGuest, type FriendView } from "@/lib/session";

const NAV = [
  { href: "/onboard", label: "Profile" },
  { href: "/upload", label: "Lookbook" },
  { href: "/taste", label: "Taste" },
  { href: "/shop", label: "Shop" },
];

/** Dims while its page loads (a first visit in dev can take seconds to compile), so a click never looks ignored. */
function Pending({ children }: { children: React.ReactNode }) {
  const { pending } = useLinkStatus();
  return <span className={pending ? "opacity-40 animate-pulse" : undefined} aria-busy={pending || undefined}>{children}</span>;
}

/** The menu is the header's headline: display-size links, the current page underlined. */
const BAR = "flex flex-wrap justify-center items-baseline gap-x-4 sm:gap-x-10 gap-y-1 px-4 py-3 text-lg sm:text-display";
const ITEM = "hover:underline underline-offset-4 decoration-1";
const CURRENT = "underline underline-offset-4 decoration-1";

/** The site wordmark, in the same swash italic as the footer. */
function Wordmark() {
  return (
    <span className="font-display italic leading-none" style={{ fontFeatureSettings: '"swsh" 1, "salt" 1' }}>
      {APP_NAME}
    </span>
  );
}

/** The site menu. In a friend view it shops for the friend, and Profile / Lookbook offer to build your own instead. */
export function SiteNav() {
  const router = useRouter();
  const pathname = usePathname();
  const isCurrent = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  const cls = (href: string) => (isCurrent(href) ? CURRENT : ITEM);
  const [friend, setFriend] = useState<FriendView | null>(null);
  const [asking, setAsking] = useState(false);

  useEffect(() => {
    const read = () => setFriend(getFriendView());
    read();
    window.addEventListener(FRIEND_EVENT, read);
    return () => window.removeEventListener(FRIEND_EVENT, read);
  }, []);

  if (!friend) {
    return (
      <nav className={BAR}>
        <Link href="/" aria-label="Home"><Pending><Wordmark /></Pending></Link>
        {NAV.map((item) => (
          <Link key={item.href} href={item.href} className={cls(item.href)} aria-current={isCurrent(item.href) ? "page" : undefined}>
            <Pending>{item.label}</Pending>
          </Link>
        ))}
      </nav>
    );
  }

  const who = friend.name || "your friend";
  return (
    <>
      <nav className={BAR}>
        <Link href="/" aria-label="Home"><Pending><Wordmark /></Pending></Link>
        <button onClick={() => setAsking(true)} className={ITEM}>Profile</button>
        <button onClick={() => setAsking(true)} className={ITEM}>Lookbook</button>
        <Link href={`/friend/${friend.token}`} className={cls(`/friend/${friend.token}`)}>
          <Pending>{friend.name ? `${friend.name}'s taste` : "Their taste"}</Pending>
        </Link>
        <Link href={`/gift/${friend.token}`} className={cls(`/gift/${friend.token}`)}>
          <Pending>Shop for {friend.name || "them"}</Pending>
        </Link>
      </nav>
      {asking && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 px-4" onClick={() => setAsking(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="own-title"
            className="bg-paper border border-ink p-6 max-w-sm w-full grid gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            <p id="own-title" className="text-display">Want to build your own taste profile?</p>
            <p className="text-sm">
              You&apos;re browsing {who}&apos;s shared taste, which is view only. Build your own to get a moodboard and
              searches made for you.
            </p>
            <div className="grid grid-cols-2 gap-2">
              <button onClick={() => setAsking(false)} className="label border border-ink px-3 py-2" autoFocus>
                Keep browsing
              </button>
              <button
                onClick={() => {
                  clearFriendView();
                  startGuest(); // a new profile for this tab, not the one already saved in this browser
                  setAsking(false);
                  router.push("/onboard");
                }}
                className="label bg-ink text-paper px-3 py-2"
              >
                Build my own
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
