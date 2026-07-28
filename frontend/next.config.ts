import type { NextConfig } from "next";

/**
 * `STATIC_EXPORT=true` produces a fully static site for GitHub Pages, which is
 * how the public landing page gets a crawlable URL. The dashboard still runs
 * normally (`npm run dev` / `npm start`) against a live backend.
 *
 * `BASE_PATH` is required because Pages serves project sites from
 * /<repo-name>/ rather than the domain root.
 */
const isStaticExport = process.env.STATIC_EXPORT === "true";
const basePath = process.env.BASE_PATH ?? "";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  ...(isStaticExport
    ? {
        output: "export",
        basePath: basePath || undefined,
        assetPrefix: basePath || undefined,
        images: { unoptimized: true },
        trailingSlash: true,
      }
    : {
        // `headers()` is unsupported in export mode; Pages sets its own anyway.
        async headers() {
          return [
            {
              source: "/(.*)",
              headers: [
                { key: "X-Content-Type-Options", value: "nosniff" },
                { key: "X-Frame-Options", value: "DENY" },
                { key: "Referrer-Policy", value: "no-referrer" },
              ],
            },
          ];
        },
      }),
};

export default nextConfig;
