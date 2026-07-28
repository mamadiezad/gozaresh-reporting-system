import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "داشبورد",
  description:
    "داشبورد آنی سامانه گزارش‌گیری: وضعیت گزارش‌ها، محاسبه‌گر چندارزی، گردش‌کار تأیید و مسیر حسابرسی.",
  // The application itself is behind authentication — no value in indexing it,
  // and it would only dilute the landing page's ranking signals.
  robots: { index: false, follow: true },
  alternates: { canonical: "/app" },
};

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return children;
}
