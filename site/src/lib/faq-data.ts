/* Single source of truth for FAQ content — the visible FAQ section
   (src/sections/faq.tsx) renders these exact strings (figures wrapped in
   StatNum by a tiny formatter), and the FAQPage JSON-LD
   (src/components/json-ld.tsx) uses the same strings verbatim. Google's FAQ
   structured-data guideline requires the marked-up text to be visible on the
   page — one copy guarantees it. */

export type FaqItem = {
  q: string;
  a: string;
};

export const faqItems: FaqItem[] = [
  {
    q: "We already have an agency. Why do we need you?",
    a: "Keep them. Your agency executes campaigns; nobody is pricing which customers will return or auditing what those campaigns are worth. We're the layer above: we hand your agency a scored segment and a forecast, and we measure what they ship — good agencies do better work against a Ledger, because a measured target beats a guess. If your agency resists being measured, that finding alone is worth the audit.",
  },
  {
    q: "Klaviyo already shows me retention data.",
    a: "Klaviyo shows what happened inside Klaviyo. It doesn't see your RTO rate, your COD failures, your Razorpay payment retries, your Shiprocket delivery times, or which acquisition cohort is quietly dying — and it will never flag that its own flows are underperforming. We read Klaviyo plus the rest of your order graph and score the whole system. Ask Klaviyo for your CIQ; it doesn't have one.",
  },
  {
    q: "Why is the audit paid when others offer free ones?",
    a: 'A free audit costs its author nothing to be wrong, and its conclusion was written before your data arrived: "hire us." The Decode is priced — ₹1,95,000 / $2,900 — so it has to stand alone: ten scores, a leak map in rupees, a 90-day plan you could hand to any team, including someone else\'s. And 100% of the fee credits against a retainer signed within 60 days, so working with us makes the audit cost nothing extra.',
  },
  {
    q: "We tried retention. It didn't work.",
    a: "What was the baseline, and what was the test? If there's no answer, that's the diagnosis: it wasn't retention that failed, it was unmeasured retention — campaigns without scores are indistinguishable from luck. Our brand promise exists because of that experience: a number, a baseline, and a deadline on every recommendation, and a monthly re-score that shows in writing whether we're earning the fee.",
  },
  {
    q: "How fast do we see results?",
    a: "The Loop Ledger is ranked by payback speed, and the fastest lines are usually leak fixes — RTO interception, failed-payment recovery — which bank inside the first quarter. Repeat-rate compounding is slower: typical engagement arithmetic covers the fee at about +1.4 points of repeat rate, and we never forecast beyond +6 points in year one, whatever a spreadsheet permits. First scores in 14 days. First re-score at day 30. First rebaseline at day 90.",
  },
  {
    q: "Do you run our campaigns, or just advise?",
    a: 'Both exist, priced separately. Ignite (₹1,50,000/mo / $2,500) is advisory: we decide, your team executes. Momentum and above (from ₹3,00,000/mo / $5,000), we operate inside your stack — Klaviyo, Interakt, your BSP — ourselves. What we never do is execution without the method: "just run our emails" is an agency engagement, and we\'re not an agency.',
  },
  {
    q: "What data access do you need?",
    a: "Read access to orders and customers in week one: Shopify, Razorpay, Shiprocket, and your messaging platforms; anything without a connector arrives as a CSV export. It's a condition of starting, not a request — you cannot score data you cannot see. Eighteen months of order history is enough. Messy is fine; the Signal Score exists to price the mess. Missing is not.",
  },
  {
    q: "What does it cost?",
    a: "All of it is on this page. The Decode: ₹1,95,000 / $2,900, one-time, 100% creditable. Retainers: ₹1,50,000–₹9,00,000 per month ($2,500–$14,000), flat, 3-month minimum, no success fees — attribution in Indian D2C is too disputable to price honestly, so accountability lives in a public monthly CIQ instead of a rev-share you'd spend every review disputing. Annual prepay takes 10% off. That is the only discount that exists.",
  },
  {
    q: "Do you work with brands outside India?",
    a: "Yes — US, UK, and Australian Shopify brands, priced in USD, delivered remotely. The method was built on the hardest version of the problem — COD economics, RTO, WhatsApp-first customers — and it travels: the scores, the models, and the Loop are identical; only the channel mix changes. If your repeat cycle is under 12 months and your data lives in Shopify, geography isn't the constraint.",
  },
];
