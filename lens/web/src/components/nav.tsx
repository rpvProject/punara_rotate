"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/cohorts", label: "Cohorts" },
  { href: "/segments", label: "Segments" },
  { href: "/revenue", label: "Revenue" },
  { href: "/leaks", label: "Leaks" },
  { href: "/predictions", label: "Predictions" },
  { href: "/experiments", label: "Experiments" },
  { href: "/customers", label: "Customers" },
];

export function Nav() {
  const path = usePathname();
  return (
    <aside className="shrink-0 border-b border-line md:w-52 md:border-b-0 md:border-r">
      <div className="flex items-center gap-6 px-6 py-5 md:flex-col md:items-stretch md:gap-0 md:px-0 md:py-0">
        <Link href="/" className="md:block md:px-6 md:pb-2 md:pt-8">
          <span className="font-display text-xl font-semibold tracking-tight text-bone">
            Punara <span className="text-marigold">Lens</span>
          </span>
          <span className="mt-1 hidden text-[11px] leading-snug text-graphite md:block">
            The science of the second order
          </span>
        </Link>
        <nav className="flex gap-1 overflow-x-auto md:mt-6 md:flex-col md:gap-0.5 md:px-3">
          {ITEMS.map((it) => {
            const active =
              it.href === "/" ? path === "/" : path.startsWith(it.href);
            return (
              <Link
                key={it.href}
                href={it.href}
                className={`whitespace-nowrap rounded px-3 py-2 text-sm transition-colors ${
                  active
                    ? "bg-panel text-bone shadow-[inset_2px_0_0_0_#f2a413]"
                    : "text-muted hover:bg-panel hover:text-bone"
                }`}
              >
                {it.label}
              </Link>
            );
          })}
        </nav>
      </div>
    </aside>
  );
}
