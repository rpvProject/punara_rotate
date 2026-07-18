# Go live: Punara static site on a GoDaddy domain

> **STATUS — BUILD READY, NOT YET LIVE.**
> The marketing site has been converted to a **static build** (`site/out/`) and a
> GitHub Pages deploy workflow is committed. Nothing is pushed or deployed. The
> steps below are **founder-only** — they need your GoDaddy login, your GitHub
> repo settings, and one free Web3Forms signup. Do them in order.
>
> You own **only the GoDaddy domain** (no hosting plan). That is enough: a free
> static host serves the site, GoDaddy just points the domain at it.
>
> Placeholder: replace **`YOUR_DOMAIN`** with your real domain (e.g. `punara.com`)
> everywhere below. Do not add `https://` when a step asks for the bare domain.

---

## A. What "live" takes — the shape of it

| Piece | Job | Cost |
|---|---|---|
| **GitHub** (`rpvProject/punara_rotate`) | Stores the source **and** runs the deploy Action that builds `site/out/`. | free |
| **GitHub Pages** | Serves the static `out/` folder over HTTPS. | free |
| **Web3Forms** | Receives contact-form submissions and emails them to your inbox. | free |
| **GoDaddy** | Owns the domain + DNS. Points `YOUR_DOMAIN` at GitHub Pages. Does **not** run anything. | you already pay for the domain |

No new account beyond Web3Forms. No server, no hosting bill.

---

## B. Get a free Web3Forms access key (do this first)

The contact form posts straight from the visitor's browser to Web3Forms, which
emails you each submission. Without a key the form quietly falls back to a
`mailto:hello@punara.com` link — it still works, but you get no in-form send.

1. Go to **https://web3forms.com**.
2. Enter the delivery inbox — use **`hello@punara.com`** (or wherever you want the
   leads to land). No password/signup; they email you the key.
3. Copy the **Access Key** (a UUID like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`).
4. Hold onto it for step C (it goes in as the `WEB3FORMS_KEY` repo Variable).

The key is **public and safe to expose** — it is tied to your inbox, not a secret.

---

## C. PRIMARY host — GitHub Pages via the committed Action

This uses the existing repo and the `deploy-site.yml` workflow already committed.
No new account.

### C1. Set the repository Variables
Repo → **Settings → Secrets and variables → Actions → the `Variables` tab →
New repository variable**. Add each (these are **Variables**, not Secrets):

| Variable | Value |
|---|---|
| `SITE_URL` | `https://YOUR_DOMAIN` |
| `BOOKING_URL` | your real Cal.com / Calendly link |
| `WEB3FORMS_KEY` | the key from step B |
| `CUSTOM_DOMAIN` | `YOUR_DOMAIN` (bare, no `https://`) |

Optional analytics (leave unset for none): `GA4_ID`, `META_PIXEL_ID`,
`LINKEDIN_TAG_ID`.

### C2. Turn on Pages
Repo → **Settings → Pages → Build and deployment → Source = "GitHub Actions"**.

### C3. Deploy
Either **push** any change under `site/**` to `main`, **or** repo →
**Actions → "Deploy site to GitHub Pages" → Run workflow**. Watch it go green.
The run prints the temporary Pages URL (`https://rpvproject.github.io/...`) — open
it to confirm the site built before you touch DNS.

### C4. Claim the custom domain in Pages
Repo → **Settings → Pages → Custom domain → enter `YOUR_DOMAIN` → Save**.
(The workflow also writes `out/CNAME` from the `CUSTOM_DOMAIN` variable, so this
survives every redeploy.) Leave **"Enforce HTTPS"** unchecked until DNS resolves
(step D), then tick it.

---

## D. GoDaddy DNS for GitHub Pages

GoDaddy: **My Products → your domain → DNS → Manage DNS.**

**Before adding anything:**
- **Delete the default parked `A @` record** (points at a GoDaddy parking IP).
- **Turn OFF Domain Forwarding** (Forwarding silently re-adds an `A` record that
  fights yours).

Then add these records:

| Type | Name | Value | Purpose |
|---|---|---|---|
| `A` | `@` | `185.199.108.153` | apex `YOUR_DOMAIN` → GitHub Pages |
| `A` | `@` | `185.199.109.153` | apex (redundant edge) |
| `A` | `@` | `185.199.110.153` | apex (redundant edge) |
| `A` | `@` | `185.199.111.153` | apex (redundant edge) |
| `CNAME` | `www` | `rpvproject.github.io` | `www.YOUR_DOMAIN` → GitHub Pages |

Notes:
- All four apex `A` records are required (GitHub's four Pages edge IPs).
- **Propagation is minutes to a few hours.** GitHub Pages shows a green check on
  the Custom domain when it verifies.
- Once verified, tick **Settings → Pages → Enforce HTTPS** — the TLS certificate
  is issued automatically; no cert to buy or install.

---

## E. Alternative static hosts (same `out/` folder)

Any static host serves the identical `site/out/`. These need a free account but
give you an **instant preview URL** before you touch DNS. Point GoDaddy at the
target shown, using the same "delete parked A + forwarding off" rule as step D.

- **Cloudflare Pages** — connect the Git repo (build dir `site`, output `out`) or
  drag-and-drop `site/out/`. Add `YOUR_DOMAIN` under the project's Custom Domains;
  Cloudflare manages the apex + `www` records for you when the domain is on
  Cloudflare, or gives you the `CNAME`/`A` target to set at GoDaddy otherwise.
- **Netlify** — drag the `site/out/` folder onto **https://app.netlify.com/drop**
  for an instant `*.netlify.app` URL, then **Domain settings → Add custom domain →
  `YOUR_DOMAIN`**; Netlify shows the apex `A` (their load-balancer IP) and
  `CNAME www → your-site.netlify.app` to enter at GoDaddy.

---

## F. Preview the production static build locally

Verify exactly what will be served, on this machine only (loopback):

```bash
cd site
npm run build     # writes site/out/
npm run preview   # python http.server on 127.0.0.1:3020, serving out/
```

Open **http://127.0.0.1:3020**. Ctrl-C to stop. (For local preview the form shows
the `mailto` fallback unless `NEXT_PUBLIC_WEB3FORMS_KEY` is set in `site/.env.local`.)

---

## G. Before you point the domain — still-open items

These are content gaps, not deploy blockers, but fix them before running real
traffic through `YOUR_DOMAIN`:

- [ ] **Founder identity** — the booking + contact sections still have an unnamed
      "note from the founder", a placeholder photo, and a placeholder LinkedIn
      link. Add the real name, photo, and LinkedIn URL (the review flagged this as
      the top conversion blocker).
- [ ] **Legal pages** — ship real **Privacy Policy** and **Terms** one-pagers
      (procurement checks for these; they were removed as dead links).
- [ ] **Test the form** — submit the live contact form once and confirm the email
      actually lands in the Web3Forms delivery inbox from step B.

---

## Want the server features back?

This runbook is the **static, $0** path (GitHub Pages). If you ever need the
server-rendered version again — live `/api/contact`, dynamic OG images — see
**`docs/DEPLOYMENT.md`**, the Vercel-oriented SSR runbook. The two are mutually
exclusive: pick static-on-Pages **or** SSR-on-Vercel, not both at once.
