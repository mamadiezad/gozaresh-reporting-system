import type { MetadataRoute } from "next";

import { SITE, absoluteUrl } from "@/lib/seo";

// Required for `output: export` (GitHub Pages build).
export const dynamic = "force-static";

const SECTIONS = ["calculations", "workflow", "dashboard", "integrations", "security"];

/**
 * The static export uses `trailingSlash: true`, so /en 301-redirects to /en/.
 * Listing the unslashed form would advertise redirect URLs and contradict the
 * canonical tags, which Google reports as "Page with redirect". Every entry
 * below therefore matches the canonical form exactly.
 */
const withSlash = (path = "/") => {
  const url = absoluteUrl(path);
  return url.endsWith("/") ? url : `${url}/`;
};

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  const languages = { fa: withSlash("/"), en: withSlash("/en") };

  return [
    {
      url: withSlash("/"),
      lastModified,
      changeFrequency: "weekly",
      priority: 1,
      alternates: { languages },
    },
    {
      url: withSlash("/en"),
      lastModified,
      changeFrequency: "weekly",
      priority: 0.9,
      alternates: { languages },
    },
    // Section anchors help Google surface jump-links for long-tail queries.
    ...SECTIONS.map((section) => ({
      url: `${withSlash("/")}#${section}`,
      lastModified,
      changeFrequency: "monthly" as const,
      priority: 0.7,
    })),
  ];
}
