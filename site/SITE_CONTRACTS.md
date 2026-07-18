# SITE_CONTRACTS — Punara marketing site

Scaffold is live: `npm run build` passes with section stubs. This file is the
contract between the five builders. Break it and you break someone else's merge.

## 1. Section order & anchor ids (fixed)

`src/app/page.tsx` renders, in order:

| # | anchor id | file (src/sections/) | named export | context |
|---|-----------|----------------------|--------------|---------|
| 1 | `hero` | `hero.tsx` | `Hero` | dark (Nightfall) |
| 2 | `proof` | `proof.tsx` | `Proof` | light |
| 3 | `problem` | `problem.tsx` | `Problem` | light |
| 4 | `solution` | `solution.tsx` | `Solution` | light |
| 5 | `services` | `services.tsx` | `Services` | light |
| 6 | `platform` | `platform.tsx` | `Platform` | light |
| 7 | `difference` | `difference.tsx` | `Difference` | light |
| 8 | `process` | `process.tsx` | `Process` | light |
| 9 | `outcomes` | `outcomes.tsx` | `Outcomes` | light |
| 10 | `faq` | `faq.tsx` | `Faq` | light |
| 11 | `book` | `book.tsx` | `Book` | dark (Nightfall) |
| 12 | `contact` | `contact.tsx` | `Contact` | light |

Keep the export name and anchor id exactly as above. Do not reorder. Do not
add/remove sections. Light/dark per section is decided by the `dark` prop on
`<Section>` — nothing else.

## 2. File ownership (5 builders — touch ONLY your files)

- **Builder A** — `src/sections/hero.tsx`, `src/sections/proof.tsx`, a new
  `src/components/dashboard-mockup.tsx` (the Lens mockup used in the hero),
  plus polish of `src/components/nav.tsx` and `src/components/footer.tsx`.
- **Builder B** — `src/sections/problem.tsx`, `src/sections/solution.tsx`,
  `src/sections/process.tsx`, `src/sections/outcomes.tsx`.
- **Builder C** — `src/sections/services.tsx`, `src/sections/platform.tsx`,
  `src/sections/difference.tsx`.
- **Builder D** — `src/sections/faq.tsx`, `src/sections/book.tsx`,
  `src/sections/contact.tsx`, `src/app/api/contact/route.ts` (new).
- **Builder E** — SEO/analytics infra only: metadata/OG in `src/app/layout.tsx`
  metadata export, `src/app/sitemap.ts`, `src/app/robots.ts`, analytics +
  cookie-consent components (new files under `src/components/`), wired via
  `hasAnalytics` from `src/lib/config.ts`. **No section files.**

Shared files (`ui.tsx`, `config.ts`, `globals.css`, `fonts.ts`, `page.tsx`)
are frozen. If a primitive is missing, flag it in your return — do not edit
shared files.

## 3. Copy rule (absolute)

**ALL visible copy comes verbatim from `site/COPY.md`.** Builders never write,
paraphrase, or "improve" copy. If COPY.md lacks a string you need (a label, an
aria-label, an empty-state), ship the section with a `TODO(copy): <what>`
comment and flag it in your return message. Never invent testimonials, client
names, or numbers.

## 4. `src/components/ui.tsx` — primitive API (exact props)

All primitives accept `className?: string` appended last (so you can extend,
not override rhythm).

- `Section` — `{ id: string; dark?: boolean; className?; children }`.
  Renders `<section id>` with the **one** vertical rhythm
  (`py-20 md:py-28`), wraps children in `Container`, and applies
  `.dark-section` when `dark`. Every page section uses it. Never add your own
  `py-*` to a section.
- `Container` — `{ className?; children }` → `mx-auto w-full max-w-6xl px-6
  md:px-10`. Only needed outside `Section` (nav/footer already use it).
- `Eyebrow` — `{ className?; children }` → mono, uppercase, tracked small
  label (`text-muted`).
- `H2` — `{ className?; children }` → Fraunces `text-3xl md:text-4xl`.
- `H3` — `{ className?; children }` → Fraunces `text-xl md:text-2xl`.
- `BodyText` — `{ className?; children }` → `<p>` `max-w-prose
  leading-relaxed text-ink/80`.
- `CTAButton` — `{ variant?: "primary" | "secondary"; href?: string;
  className?; children }`. **`href` defaults to `config.bookingUrl`** — every
  "Book a Strategy Call" button just omits `href`. `primary` =
  marigold-on-nightfall; `secondary` = ghost border. Renders an `<a>`.
- `StatNum` — `{ className?; children }` → `<span class="num">` (IBM Plex
  Mono, tabular-nums). **Every numeral on the page goes through this or the
  `.num` class.**
- `Card` — `{ className?; children }` → single border on `bg-surface`,
  `rounded-lg p-6`. **Never nest a Card inside a Card.**
- `Divider` — `{ className? }` → `<hr>` on `border-line`.

## 5. Tokens (globals.css — canon `_canon.md` §12, same as Lens)

Fixed palette (Tailwind classes `bg-*` / `text-*` / `border-*`):
`nightfall #101623`, `bone #FAF7F0`, `marigold #F2A413`, `teal #0FA284`,
`ember #E0533D`, `graphite #5A6272`, `panel #151C2B`, `panel2 #1B2334`.

Contextual tokens — **use these by default**; they flip automatically inside
`.dark-section`: `bg`, `ink`, `surface`, `line`, `muted`
(e.g. `text-ink`, `bg-surface`, `border-line`, `text-muted`).

Semantics: **teal = positive/data wins, ember = leak/risk, marigold = "act
here" only** (CTAs, one accent per screen). Never decorative gradients, never
marigold body text.

Fonts (set in `src/app/fonts.ts`, exposed as Tailwind `font-display`
(Fraunces), `font-sans` (Inter), `font-mono` (IBM Plex Mono)). Numerals are
always mono+tabular (`StatNum` / `.num`).

## 6. Rhythm & layout rules

- One vertical rhythm: `Section`'s `py-20 md:py-28`. No exceptions.
- One content width: `Container`'s `max-w-6xl px-6 md:px-10`.
- Whitespace over boxes. Max one level of `Card`. No card-in-card-in-card.
- No gradient blobs, no glassmorphism, no stock illustration.
- Anchors: nav links point at the ids in §1 — if your section renders its own
  wrapper instead of `Section`, anchors break; don't.

## 7. Config (`src/lib/config.ts`)

Import `config` / `hasAnalytics` — never read `process.env` anywhere else.
Keys: `bookingUrl`, `platformUrl`, `siteUrl`, `ga4Id`, `metaPixelId`,
`linkedInTagId`. Analytics scripts and the cookie banner render **only** when
`hasAnalytics` is true. Documented in `.env.example`.

## 8. Build gate

`npm run build` (from `site/`) must pass before you hand back. Screenshots go
in `site/.screenshots/` (gitignored).

## 9. Builder E coordination notes (SEO/analytics infra — landed)

- **FAQ single source: `src/lib/faq-data.ts`.** Exports `faqItems: FaqItem[]`
  with `q`/`a` (on-page copy, COPY.md §11 verbatim) and `schemaQ`/`schemaA`
  (plain-text JSON-LD pairs, COPY.md §15 verbatim). **Builder D: render the
  FAQ section from `faqItems` (`q`/`a`) — do not re-type the copy.** The
  FAQPage JSON-LD (`src/components/json-ld.tsx`) reads the same array, so
  page and schema cannot drift.
- **Layout wiring (Builder E-owned):** `src/app/layout.tsx` now renders
  `<JsonLd />` and, when `hasAnalytics`, `<Analytics />` + `<CookieConsent />`
  (consent-gated via localStorage key `punara-consent`; decline = no scripts).
  Also final metadata (title/description/canonical/OG/twitter/robots) and
  `src/app/{opengraph-image.tsx,sitemap.ts,robots.ts}`.
- **globals.css additive-only change (coordinated here, not a restyle):**
  a global `:focus-visible` ring on `var(--ink)` and a
  `prefers-reduced-motion` opt-out for smooth scroll. No token or primitive
  changed.
- **Copy gap:** cookie-consent banner text + Accept/Decline labels are not in
  COPY.md — placeholder text shipped with a `TODO(copy)` in
  `src/components/cookie-consent.tsx`.
