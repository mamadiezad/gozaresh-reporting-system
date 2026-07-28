import type { MetadataRoute } from "next";

import { SITE, absoluteUrl } from "@/lib/seo";

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();

  return [
    { url: SITE.url, lastModified, changeFrequency: "weekly", priority: 1 },
    ...["calculations", "workflow", "dashboard", "integrations", "security"].map((section) => ({
      url: absoluteUrl(`/#${section}`),
      lastModified,
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
  ];
}
