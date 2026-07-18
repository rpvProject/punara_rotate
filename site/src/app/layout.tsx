import type { Metadata, Viewport } from "next";
import "./globals.css";
import { fontClasses } from "./fonts";
import { Nav } from "@/components/nav";
import { Footer } from "@/components/footer";
import { Analytics } from "@/components/analytics";
import { CookieConsent } from "@/components/cookie-consent";
import { JsonLd } from "@/components/json-ld";
import { config, hasAnalytics } from "@/lib/config";

/* All strings verbatim from site/COPY.md §15 (SEO pack). */
const ogTitle = "Your first order is a cost. Your second order is a business.";
const ogDescription =
  "Retention Intelligence for Shopify D2C: the Punara Ten scores, a revenue-leak map in rupees, and the Compounding Loop — Decode, Design, Drive, Compound.";

export const metadata: Metadata = {
  metadataBase: new URL(config.siteUrl),
  title: "Punara — Retention Intelligence for Shopify D2C Brands",
  description:
    "Ten scores, one CIQ, recommendations priced in rupees. Punara makes repeat revenue a measured system for Shopify D2C brands doing ₹10–200 crore ($1M–$25M).",
  alternates: { canonical: "/" },
  openGraph: {
    type: "website",
    url: "/",
    siteName: "Punara",
    title: ogTitle,
    description: ogDescription,
  },
  twitter: {
    card: "summary_large_image",
    title: ogTitle,
    description: ogDescription,
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
};

export const viewport: Viewport = {
  themeColor: "#101623",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${fontClasses} h-full antialiased`}>
      <body className="min-h-full">
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <Nav />
        <main id="main">{children}</main>
        <Footer />
        <JsonLd />
        {hasAnalytics && (
          <>
            <Analytics />
            <CookieConsent />
          </>
        )}
      </body>
    </html>
  );
}
