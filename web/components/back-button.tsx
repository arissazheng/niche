"use client";

import { useRouter } from "next/navigation";

export function BackButton() {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => window.history.length > 1 ? router.back() : router.push("/")}
      className="rule-t rule-b text-display py-2 text-center"
    >
      Back
    </button>
  );
}
