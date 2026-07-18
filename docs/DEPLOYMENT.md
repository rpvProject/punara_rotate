# Deploying the Punara site + connecting a GoDaddy domain

> **STATUS: NOT DEPLOYED. Local-only until the founder approves.**
> This is a runbook to follow *later*. Nothing here has been executed. Do not
> run any of it — or push to a host — without explicit sign-off.

---

## The three roles (who does what)

| Piece | Job |
|---|---|
| **GitHub** (`rpvProject/punara_rotate`) | Stores the source. A host reads from it. |
| **A host** (Vercel, etc.) | Actually *runs* the Next.js app and serves it over HTTPS. |
| **GoDaddy** | Owns the domain and its DNS. Points the domain at the host. **GoDaddy does not run the app** — its shared hosting is for PHP/WordPress, not Next.js. |

The site is **not static**: it has a live API route (`/api/contact`), dynamically
generated OG images, and server-rendered metadata. So it needs a host that runs
Next.js. GoDaddy's role is only the domain + DNS.

The repo is a **monorepo** — the site lives in the `site/` subdirectory
(alongside `lens/`). Whatever host you use, its **root/base directory must be
`site/`**, not the repo root.

---

## Pre-flight — clear these BEFORE going public

These are real gaps that only matter once the site is reachable by strangers:

1. **Contact form storage.** `site/src/app/api/contact/route.ts` appends
   submissions to a local file. On serverless hosts (Vercel) the filesystem is
   read-only/ephemeral — **submissions will be lost**. Plug in a mail provider at
   the marked line (line ~58): e.g. Resend `await resend.emails.send({ to: "hello@punara.com", ... })`.
   Add `RESEND_API_KEY` as a host env var (server-side, **not** `NEXT_PUBLIC_`).
2. **Real env values** (see the table below) — especially `NEXT_PUBLIC_SITE_URL`,
   which drives canonical URLs, the sitemap, and OG tags. If it's wrong, SEO points
   at the wrong domain.
3. **Founder identity.** The booking section has an unnamed "note from the founder"
   and a placeholder LinkedIn link. Add a real name, photo, and LinkedIn URL — the
   review flagged this as the top conversion blocker.
4. **Legal pages.** Privacy Policy / Terms / DPDP grievance contact were removed as
   dead links. Ship real one-pagers before running traffic (procurement checks these).
5. **Analytics** (optional). Set the GA4 / Meta / LinkedIn IDs only if you want
   tracking — the cookie-consent banner appears automatically when any is set, and
   scripts load only after consent.

---

## Environment variables (set these on the host)

| Variable | Set to | Notes |
|---|---|---|
| `NEXT_PUBLIC_SITE_URL` | `https://YOURDOMAIN` | Canonical base. Must be the real https domain. |
| `NEXT_PUBLIC_BOOKING_URL` | your Cal.com/Calendly URL | Every "Book a Strategy Call" CTA. Cal.com/Calendly URLs also enable the inline embed. |
| `NEXT_PUBLIC_PLATFORM_URL` | *leave unset* | Lens stays local/private; unset → the "Explore Platform" CTA degrades to the on-page `#platform` anchor (no dead link). |
| `NEXT_PUBLIC_GA4_ID` | optional | e.g. `G-XXXXXXX`. Empty = no tracking. |
| `NEXT_PUBLIC_META_PIXEL_ID` | optional | Empty = no tracking. |
| `NEXT_PUBLIC_LINKEDIN_TAG_ID` | optional | Empty = no tracking. |
| `RESEND_API_KEY` (or SMTP) | required for the form | Server-side only. Not `NEXT_PUBLIC_`. |

Replace `YOURDOMAIN` throughout with the domain you own on GoDaddy
(canon candidates: `punara.com` / `punara.in` / `punara.io`).

---

## Recommended path — Vercel + GoDaddy

Free, first-class Next.js support, auto-deploys on every `git push`, keeps the
form + dynamic images working. GoDaddy stays as just the domain.

### 1. Import the repo
- vercel.com → **Add New → Project** → import `rpvProject/punara_rotate`.
- **Root Directory: `site`** (critical — it's a monorepo).
- Framework preset: **Next.js** (auto-detected). Build command / output: defaults.

### 2. Add env vars
- Project → **Settings → Environment Variables** → add the rows above (Production).
- Redeploy so they take effect.

### 3. Add the domain in Vercel
- Project → **Settings → Domains** → add `YOURDOMAIN` and `www.YOURDOMAIN`.
- Vercel shows the exact DNS records to create. **Use what Vercel shows** — the
  values below are the current known defaults for reference.

### 4. Set the records in GoDaddy
GoDaddy: **My Products → your domain → DNS / Manage DNS**.

- **First remove GoDaddy's defaults** that conflict: the parked `A @` record
  (points at a GoDaddy parking IP) and any **Domain Forwarding** (it silently
  re-adds an A record). Forwarding off, parking record deleted.
- Then add:

| Type | Name | Value | Purpose |
|---|---|---|---|
| `A` | `@` | `76.76.21.21` | Apex (`YOURDOMAIN`) → Vercel. GoDaddy can't CNAME the apex, so it's an A record. |
| `CNAME` | `www` | `cname.vercel-dns.com` | `www.YOURDOMAIN` → Vercel. |

- SSL/HTTPS is issued automatically by Vercel once DNS resolves.
- Propagation: usually minutes, up to a few hours. Vercel's Domains page shows a
  green check when it's live.

### 5. Auto-deploy
Once connected, every push to the branch Vercel watches redeploys the site. Our
publish flow (code committed to local `main` → merged onto the `public` branch →
pushed) already keeps the blueprint out of the public repo, so nothing sensitive
reaches the host.

---

## Alternative — GitHub Pages (static), only if you want $0 and no host

GitHub Pages serves **static files only**. To use it you must:
- Add `output: "export"` to `next.config.ts` and rebuild — **this disables the
  `/api/contact` route** (move the form to a service like Formspree, or a
  `mailto:`) and makes the OG image static.
- Enable Pages on the repo, add a `CNAME` file with `YOURDOMAIN`.
- In GoDaddy DNS:

| Type | Name | Value |
|---|---|---|
| `A` | `@` | `185.199.108.153` |
| `A` | `@` | `185.199.109.153` |
| `A` | `@` | `185.199.110.153` |
| `A` | `@` | `185.199.111.153` |
| `CNAME` | `www` | `rpvproject.github.io` |

Trade-off: free and simple, but you lose the working contact form and dynamic
images. Not recommended for a lead-gen site whose whole job is the form.

---

## Verify (after going live)

- `https://YOURDOMAIN` loads over HTTPS, hero renders.
- `https://YOURDOMAIN/sitemap.xml` and `/robots.txt` return 200 and reference the
  real domain.
- Submit the contact form → confirm the email actually arrives (the fs blocker above).
- "Book a Strategy Call" opens the real calendar.
- Check OG preview (e.g. paste the URL into a Slack/LinkedIn message draft).

## Rollback / back to local

Nothing about the local setup changes. `npm run dev -- -p 3020 -H 127.0.0.1` still
works. To take the public site down: remove the domain in the host, or in GoDaddy
delete the A/CNAME records. To fully unpublish: delete the Vercel project.

> DNS IPs and CNAME targets above are provider-managed and can change. Always
> prefer the exact records the host's dashboard shows you at setup time.
