import { config } from "@/lib/config";
import { faqItems } from "@/lib/faq-data";

/* Structured data: Organization + ProfessionalService + FAQPage in one @graph.
   FAQ pairs come from src/lib/faq-data.ts — the same module the visible FAQ
   section consumes, so page and schema cannot drift. Prices verbatim from
   blueprint/_canon.md §8. Server component; rendered once in layout. */

const graph = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": `${config.siteUrl}/#organization`,
      name: "Punara",
      url: config.siteUrl,
      email: "hello@punara.com",
      description:
        "Punara is the Retention Intelligence firm for Shopify D2C brands — ten scores, one CIQ, and recommendations priced in rupees. The science of the second order.",
      sameAs: ["https://linkedin.com/company/punara"],
    },
    {
      "@type": "ProfessionalService",
      "@id": `${config.siteUrl}/#service`,
      name: "Punara Advisory",
      url: config.siteUrl,
      parentOrganization: { "@id": `${config.siteUrl}/#organization` },
      description:
        "Retention marketing and customer intelligence consultancy for Shopify D2C brands, powered by Punara Lens.",
      areaServed: [
        { "@type": "Country", name: "India" },
        { "@type": "Country", name: "United States" },
        { "@type": "Country", name: "United Kingdom" },
        { "@type": "Country", name: "Australia" },
      ],
      priceRange: "₹1,50,000–₹9,00,000/mo ($2,500–$14,000)",
      makesOffer: {
        "@type": "Offer",
        name: "The Punara Decode",
        description:
          "One-time 3-week audit: all ten scores + CIQ, revenue-leak map quantified in rupees, 90-day Loop Ledger. 100% creditable against any retainer signed within 60 days. Never free.",
        price: "195000",
        priceCurrency: "INR",
      },
    },
    {
      "@type": "FAQPage",
      "@id": `${config.siteUrl}/#faq`,
      mainEntity: faqItems.map((f) => ({
        "@type": "Question",
        name: f.q,
        acceptedAnswer: { "@type": "Answer", text: f.a },
      })),
    },
  ],
};

export function JsonLd() {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{
        __html: JSON.stringify(graph).replace(/</g, "\\u003c"),
      }}
    />
  );
}
