import type { NextConfig } from "next";

/* Two hosting modes from one config:
   - Default (Vercel / any Next.js-native host): NO static export. Vercel runs
     the app and serves every route correctly. This is the mode that must be the
     default — `output: "export"` makes Vercel serve 404s.
   - Static hosts (GitHub Pages / GoDaddy): build with STATIC_EXPORT=1 to emit a
     pure-static out/ folder. basePath/assetPrefix (NEXT_PUBLIC_BASE_PATH) let a
     project-pages sub-path resolve assets; a custom domain leaves it empty. */
const staticExport = process.env.STATIC_EXPORT === "1";
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig: NextConfig = {
  images: { unoptimized: true },
  ...(staticExport ? { output: "export", trailingSlash: true } : {}),
  ...(basePath ? { basePath, assetPrefix: basePath } : {}),
};

export default nextConfig;
