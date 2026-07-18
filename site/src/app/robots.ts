import type { MetadataRoute } from "next";
import { config } from "@/lib/config";

// Required by `output: export` in Next 16 — emit robots.txt at build time.
export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${config.siteUrl}/sitemap.xml`,
  };
}
