"use client";

import { useSyncExternalStore } from "react";

/* Consent state shared with src/components/analytics.tsx. localStorage-backed;
   a window event keeps both components in sync without a reload, so accepting
   injects analytics immediately and declining never injects anything. */

const KEY = "punara-consent";
const EVENT = "punara-consent";

export type Consent = "accepted" | "declined" | null;

function read(): Consent {
  try {
    const v = localStorage.getItem(KEY);
    return v === "accepted" || v === "declined" ? v : null;
  } catch {
    return null;
  }
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}

/* localStorage is an external store — useSyncExternalStore keeps Analytics
   and the banner in sync without effects. Server snapshot is null (no choice
   known during SSR); React re-reads on the client after hydration. */
export function useConsent(): Consent {
  return useSyncExternalStore(subscribe, read, () => null);
}

function save(value: "accepted" | "declined") {
  try {
    localStorage.setItem(KEY, value);
  } catch {
    /* storage unavailable — treat as session-only choice */
  }
  window.dispatchEvent(new Event(EVENT));
}

/* Rendered from layout only when hasAnalytics is true. Hidden once a choice
   is stored. TODO(copy): cookie-banner text is not in COPY.md — the two
   sentences and button labels below are functional placeholders, flagged. */
export function CookieConsent() {
  const consent = useConsent();
  if (consent !== null) return null;

  return (
    <aside
      aria-label="Cookie consent"
      className="fixed inset-x-4 bottom-4 z-50 mx-auto max-w-xl rounded-lg border border-line bg-surface p-4 shadow-lg md:inset-x-auto md:right-6"
    >
      <p className="text-sm leading-relaxed text-ink/80">
        We use analytics cookies to understand how this site is used. Nothing
        runs unless you accept.
      </p>
      <div className="mt-3 flex gap-3">
        <button
          type="button"
          onClick={() => save("accepted")}
          className="rounded-md bg-marigold px-4 py-2 text-sm font-medium text-nightfall hover:bg-marigold/90"
        >
          Accept
        </button>
        <button
          type="button"
          onClick={() => save("declined")}
          className="rounded-md border border-line px-4 py-2 text-sm text-ink hover:border-graphite"
        >
          Decline
        </button>
      </div>
    </aside>
  );
}
