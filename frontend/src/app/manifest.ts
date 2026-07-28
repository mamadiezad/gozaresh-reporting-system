import type { MetadataRoute } from "next";

import { SITE } from "@/lib/seo";

// Required for `output: export` (GitHub Pages build).
export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE.name,
    short_name: SITE.shortName,
    description: SITE.description,
    start_url: "/app",
    display: "standalone",
    background_color: "#0f1420",
    theme_color: "#0f1420",
    lang: "fa-IR",
    dir: "rtl",
    categories: ["business", "finance", "productivity"],
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
    ],
  };
}
