"use client";

import { useEffect } from "react";

/** Right-hand panel with a black top bar, like the shopping-bag drawer in the reference. */
export function Drawer({ open, onClose, children }: { open: boolean; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[1000] flex justify-end" role="dialog" aria-modal>
      <button aria-label="Close" className="absolute inset-0 cursor-default" onClick={onClose} />
      <aside className="relative h-full w-full max-w-md overflow-y-auto bg-paper border-l border-ink shadow-[-8px_0_24px_rgba(0,0,0,.18)]">
        <div className="bg-ink h-3" />
        <div className="rule-b flex justify-end px-4 py-2">
          <button onClick={onClose} className="text-xl leading-none" aria-label="Close">×</button>
        </div>
        <div className="p-4">{children}</div>
      </aside>
    </div>
  );
}
