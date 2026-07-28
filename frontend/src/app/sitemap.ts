import type { MetadataRoute } from "next";

import { SITE, absoluteUrl } from "@/lib/seo";

// Required for `output: export` (GitHub Pages build).
export const dynamic = "force-static";

const SECTIONS = ["calculations", "workflow", "dashboard", "integrations", "security"];

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  const languages = { fa: SITE.url, en: absoluteUrl("/en") };

  return [
    {
      url: SITE.url,
      lastModified,
      changeFrequency: "weekly",
      priority: 1,
      alternates: { languages },
    },
    {
      url: absoluteUrl("/en"),
      lastModified,
      changeFrequency: "weekly",
      priority: 0.9,
      alternates: { languages },
    },
    ...SECTIONS.map((section) => ({
      url: absoluteUrl(`/#${section}`),
      lastModified,
      changeFrequency: "monthly" as const,
      priority: 0.7,
    })),
  ];
}
