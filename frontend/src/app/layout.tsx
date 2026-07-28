import type { Metadata, Viewport } from "next";

import { SITE, absoluteUrl, structuredData } from "@/lib/seo";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: {
    default: SITE.title,
    template: `%s | ${SITE.shortName}`,
  },
  description: SITE.description,
  keywords: [...SITE.keywords],
  authors: [{ name: SITE.author, url: SITE.authorTelegram }],
  creator: SITE.author,
  publisher: SITE.author,
  applicationName: SITE.shortName,
  generator: "Next.js",
  referrer: "no-referrer",
  category: "finance",

  alternates: {
    canonical: "/",
    languages: { "fa-IR": "/", "x-default": "/" },
  },

  openGraph: {
    type: "website",
    locale: SITE.locale,
    url: SITE.url,
    siteName: SITE.name,
    title: SITE.title,
    description: SITE.description,
    images: [
      {
        url: absoluteUrl("/og.png"),
        width: 1200,
        height: 630,
        alt: SITE.name,
      },
    ],
  },

  twitter: {
    card: "summary_large_image",
    title: SITE.title,
    description: SITE.description,
    images: [absoluteUrl("/og.png")],
  },

  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },

  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icon.svg" }],
  },

  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0f1420" },
    { media: "(prefers-color-scheme: light)", color: "#f5f7fb" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <head>
        <script
          type="application/ld+json"
          // Structured data must be inlined; the content is generated from our
          // own constants, never from user input.
          dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData()) }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
