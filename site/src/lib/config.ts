/* Single source of truth for all NEXT_PUBLIC_* env. Import `config` — never
   read process.env elsewhere. Values are inlined at build time. */

const rawPlatformUrl =
  process.env.NEXT_PUBLIC_PLATFORM_URL || "http://127.0.0.1:3010";
const isLocalhost = /^https?:\/\/(127\.0\.0\.1|localhost)/i.test(rawPlatformUrl);

export const config = {
  /** Every "Book a Strategy Call" CTA links here. */
  bookingUrl:
    process.env.NEXT_PUBLIC_BOOKING_URL || "https://cal.com/punara/strategy",
  /** True only when a real booking URL was provided — the inline calendar
      embed renders only then; the default placeholder URL would 404 inside
      the iframe at the exact conversion moment. */
  bookingUrlSet: Boolean(process.env.NEXT_PUBLIC_BOOKING_URL),
  /** "Explore Platform" CTA — Punara Lens. In production a missing/localhost
      value falls back to the on-page #platform section instead of shipping a
      dead link to every visitor. */
  platformUrl:
    process.env.NODE_ENV === "production" && isLocalhost
      ? "#platform"
      : rawPlatformUrl,
  /** Canonical base URL (metadataBase, sitemap, OG). */
  siteUrl: process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3020",
  /** Public Web3Forms access key (safe in NEXT_PUBLIC_) — the contact form
      posts to Web3Forms from the visitor's browser. Empty = no server to
      submit to, so the form degrades to the email/mailto fallback. */
  web3formsKey: process.env.NEXT_PUBLIC_WEB3FORMS_KEY || "",
  /** Analytics — empty string means "do not render the script". */
  ga4Id: process.env.NEXT_PUBLIC_GA4_ID || "",
  metaPixelId: process.env.NEXT_PUBLIC_META_PIXEL_ID || "",
  linkedInTagId: process.env.NEXT_PUBLIC_LINKEDIN_TAG_ID || "",
} as const;

/** The contact form submits to Web3Forms only when a key is configured;
    otherwise it shows the email/mailto fallback. */
export const web3formsSet = Boolean(config.web3formsKey);

/** Cookie-consent banner + analytics scripts render only when this is true. */
export const hasAnalytics = Boolean(
  config.ga4Id || config.metaPixelId || config.linkedInTagId,
);
