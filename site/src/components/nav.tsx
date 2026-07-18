"use client";

import { useEffect, useRef, useState } from "react";
import { CTAButton } from "@/components/ui";

/* Anchor links verbatim from site/COPY.md §1. */
const links = [
  { href: "#solution", label: "Method" },
  { href: "#services", label: "Services" },
  { href: "#platform", label: "Platform" },
  { href: "#process", label: "Pricing" },
  { href: "#faq", label: "FAQ" },
];

export function Nav() {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const toggleRef = useRef<HTMLButtonElement>(null);

  /* Escape closes; Tab is trapped inside the open mobile menu. */
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        toggleRef.current?.focus();
        return;
      }
      if (e.key !== "Tab" || !menuRef.current) return;
      /* The toggle (the visible "Close" control) lives outside menuRef in the
         header bar — include it in the cycle so it stays keyboard-reachable. */
      const focusables = [
        toggleRef.current,
        ...Array.from(
          menuRef.current.querySelectorAll<HTMLElement>("a, button"),
        ),
      ].filter((el): el is HTMLElement => Boolean(el));
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    menuRef.current?.querySelector<HTMLElement>("a")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  /* Active link follows the section nearest the top of the viewport. */
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) setActive(`#${e.target.id}`);
        }
      },
      { rootMargin: "-40% 0px -55% 0px" },
    );
    for (const l of links) {
      const el = document.getElementById(l.href.slice(1));
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  const linkClass = (href: string) =>
    href === active
      ? "text-sm text-ink transition-colors"
      : "text-sm text-muted transition-colors hover:text-ink";

  return (
    <header className="dark-section sticky top-0 z-50 border-b border-line">
      {/* sticky bar height — keep anchor targets clear of it */}
      <style>{`[id] { scroll-margin-top: 4.75rem; }`}</style>
      <nav
        aria-label="Main"
        className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4 md:px-10"
      >
        <a href="#hero" className="font-display text-lg tracking-tight">
          Punara
        </a>
        <div className="hidden items-center gap-8 md:flex">
          {links.map((l) => (
            <a
              key={l.href}
              href={l.href}
              aria-current={l.href === active ? "true" : undefined}
              className={linkClass(l.href)}
            >
              {l.label}
            </a>
          ))}
          <CTAButton compact>Book a Strategy Call</CTAButton>
        </div>
        {/* Mobile: the Marigold action stays visible in the bar — the page is
            ~24k px tall and the hamburger must not be the only path to it. */}
        <div className="flex items-center gap-4 md:hidden">
          <CTAButton compact>Book a call</CTAButton>
          <button
            ref={toggleRef}
            type="button"
            className="font-mono text-xs uppercase tracking-[0.14em]"
            aria-expanded={open}
            aria-controls="mobile-menu"
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Close" : "Menu"}
          </button>
        </div>
      </nav>
      {open && (
        <div
          id="mobile-menu"
          ref={menuRef}
          className="border-t border-line px-6 py-6 md:hidden"
        >
          <div className="flex flex-col gap-5">
            {links.map((l) => (
              <a
                key={l.href}
                href={l.href}
                aria-current={l.href === active ? "true" : undefined}
                className={linkClass(l.href)}
                onClick={() => setOpen(false)}
              >
                {l.label}
              </a>
            ))}
            <CTAButton className="text-center">Book a Strategy Call</CTAButton>
          </div>
        </div>
      )}
    </header>
  );
}
