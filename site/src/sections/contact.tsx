"use client";

import { useState, type FormEvent } from "react";
import { BodyText, H2, Section, StatNum } from "@/components/ui";
import { config, web3formsSet } from "@/lib/config";

/* Contact — copy verbatim from site/COPY.md §13. Two columns on desktop:
   form left, direct-contact facts right. Errors are announced via
   aria-describedby + text (never colour alone). The hidden `website` field is
   a honeypot — humans never see it, bots fill it; it is sent as Web3Forms'
   `botcheck` so a filled value is silently dropped server-side.

   Static build: the form submits from the visitor's browser straight to
   Web3Forms when NEXT_PUBLIC_WEB3FORMS_KEY is set. With no key (local dev or
   not yet configured) it degrades to a mailto: fallback — never a dead form. */

const BANDS = [
  "Under ₹10 crore",
  "₹10–50 crore",
  "₹50–200 crore",
  "Over ₹200 crore",
  "Outside India (USD)",
];

const inputCls =
  "w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:border-graphite focus:outline-none focus:ring-1 focus:ring-graphite";
const labelCls = "mb-1.5 block text-sm font-medium text-ink";

type Errors = { name?: string; email?: string; message?: string };

export function Contact() {
  const [errors, setErrors] = useState<Errors>({});
  const [status, setStatus] = useState<"idle" | "sending" | "ok" | "fail">(
    "idle",
  );

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    // No key configured → no submit path; the mailto fallback renders instead.
    if (!web3formsSet) return;
    const form = e.currentTarget;
    const data = new FormData(form);
    const get = (k: string) => String(data.get(k) ?? "").trim();

    const next: Errors = {};
    if (!get("name")) next.name = "We need a name to reply to.";
    if (!/^\S+@\S+\.\S+$/.test(get("email")))
      next.email = "That email doesn't look complete.";
    if (!get("message"))
      next.message = "A sentence or two helps us prepare a useful reply.";
    setErrors(next);
    const firstBad = (["name", "email", "message"] as const).find(
      (k) => next[k],
    );
    if (firstBad) {
      document.getElementById(`contact-${firstBad}`)?.focus();
      return;
    }

    setStatus("sending");
    try {
      const res = await fetch("https://api.web3forms.com/submit", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({
          access_key: config.web3formsKey,
          name: get("name"),
          email: get("email"),
          brand: get("brand"),
          band: get("band"),
          message: get("message"),
          subject: "New Punara strategy-call enquiry",
          from_name: get("name"),
          // Honeypot → Web3Forms botcheck: empty for humans, filled for bots
          // (Web3Forms then drops it silently and still reports success).
          botcheck: get("website"),
        }),
      });
      const result = (await res.json()) as { success?: boolean };
      if (!result.success) throw new Error("web3forms");
      form.reset();
      setStatus("ok");
    } catch {
      setStatus("fail");
    }
  }

  const err = (field: keyof Errors) =>
    errors[field] ? (
      <p id={`contact-${field}-error`} className="mt-1.5 text-sm text-ember-text">
        {errors[field]}
      </p>
    ) : null;

  return (
    <Section id="contact">
      <div className="max-w-2xl">
        <H2>Prefer writing first?</H2>
        <BodyText className="mt-4">
          Tell us what&rsquo;s stuck. A person replies within one business day
          — we read every message because there are{" "}
          <StatNum>three slots</StatNum> and we choose carefully too.
        </BodyText>
      </div>

      <div className="mt-12 grid gap-12 md:grid-cols-[3fr_2fr] md:gap-16">
        <form onSubmit={onSubmit} noValidate className="space-y-5">
          <div>
            <label htmlFor="contact-name" className={labelCls}>
              Name
            </label>
            <input
              id="contact-name"
              name="name"
              type="text"
              autoComplete="name"
              placeholder="Your name"
              className={inputCls}
              aria-invalid={Boolean(errors.name)}
              aria-describedby={errors.name ? "contact-name-error" : undefined}
            />
            {err("name")}
          </div>

          <div>
            <label htmlFor="contact-email" className={labelCls}>
              Work email
            </label>
            <input
              id="contact-email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@yourbrand.com"
              className={inputCls}
              aria-invalid={Boolean(errors.email)}
              aria-describedby={
                errors.email ? "contact-email-error" : undefined
              }
            />
            {err("email")}
          </div>

          <div>
            <label htmlFor="contact-brand" className={labelCls}>
              Brand &amp; store URL
            </label>
            <input
              id="contact-brand"
              name="brand"
              type="text"
              placeholder="yourbrand.com or yourbrand.myshopify.com"
              className={inputCls}
            />
          </div>

          <div>
            <label htmlFor="contact-band" className={labelCls}>
              Annual revenue band
            </label>
            <select
              id="contact-band"
              name="band"
              defaultValue=""
              className={inputCls}
            >
              <option value="">Select a band</option>
              {BANDS.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="contact-message" className={labelCls}>
              What&rsquo;s on your mind
            </label>
            <textarea
              id="contact-message"
              name="message"
              rows={5}
              placeholder='e.g. "Repeat rate has been stuck at 19% for a year and nobody owns the number."'
              className={inputCls}
              aria-invalid={Boolean(errors.message)}
              aria-describedby={
                errors.message ? "contact-message-error" : undefined
              }
            />
            {err("message")}
          </div>

          {/* Honeypot — visually hidden, skipped by keyboard and AT. */}
          <div className="hidden" aria-hidden="true">
            <label htmlFor="contact-website">Website</label>
            <input
              id="contact-website"
              name="website"
              type="text"
              tabIndex={-1}
              autoComplete="off"
            />
          </div>

          {web3formsSet ? (
            <>
              <button
                type="submit"
                disabled={status === "sending"}
                className="inline-block rounded-md bg-marigold px-6 py-3 text-sm font-medium text-nightfall transition-colors hover:bg-marigold/90 disabled:opacity-60"
              >
                Send message
              </button>

              <div aria-live="polite">
                {status === "ok" && (
                  <p className="text-sm text-teal-text">
                    Got it. A reply within one business day — from a person who
                    has read your message, not an autoresponder.
                  </p>
                )}
                {status === "fail" && (
                  <p className="text-sm text-ember-text">
                    That didn&rsquo;t send. Email us directly at{" "}
                    <a href="mailto:hello@punara.com" className="underline">
                      hello@punara.com
                    </a>{" "}
                    — it reaches the same inbox.
                  </p>
                )}
              </div>
            </>
          ) : (
            /* No submit endpoint configured — never a dead form. */
            <div className="space-y-2">
              <a
                href="mailto:hello@punara.com?subject=New%20Punara%20strategy-call%20enquiry"
                className="inline-block rounded-md bg-marigold px-6 py-3 text-sm font-medium text-nightfall transition-colors hover:bg-marigold/90"
              >
                Email us at hello@punara.com
              </a>
              <p className="text-sm text-muted">
                This opens your email app — a person reads every message and
                replies within one business day.
              </p>
            </div>
          )}
        </form>

        {/* Phone and registered-office rows return only when real values
            exist — never render "XXXXX" or bracketed placeholders. */}
        <dl className="space-y-6 text-sm">
          <div>
            <dt className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
              Email
            </dt>
            <dd className="mt-1 text-ink">
              <a href="mailto:hello@punara.com" className="underline">
                hello@punara.com
              </a>
            </dd>
          </div>
          <div>
            <dt className="font-mono text-xs uppercase tracking-[0.2em] text-muted">
              LinkedIn
            </dt>
            <dd className="mt-1 text-ink">
              <a
                href="https://linkedin.com/company/punara"
                target="_blank"
                rel="noopener noreferrer"
                className="underline"
              >
                linkedin.com/company/punara
              </a>
            </dd>
          </div>
        </dl>
      </div>
    </Section>
  );
}
