import type { MetadataRoute } from "next";
import { config } from "@/lib/config";

// Required by `output: export` in Next 16 — emit sitemap.xml at build time.
export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: config.siteUrl,
      lastModified: new Date(),
      changeFrequency: "monthly",
      priority: 1,
    },
  ];
}
