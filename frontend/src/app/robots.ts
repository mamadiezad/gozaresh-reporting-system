import type { MetadataRoute } from "next";

import { absoluteUrl } from "@/lib/seo";

// Required for `output: export` (GitHub Pages build).
export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // The dashboard is behind authentication; crawling it wastes budget.
        disallow: ["/app", "/api/"],
      },
    ],
    sitemap: absoluteUrl("/sitemap.xml"),
  };
}
