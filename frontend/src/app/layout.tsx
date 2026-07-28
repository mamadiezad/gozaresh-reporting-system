import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "سامانه گزارش‌گیری سازمانی گزارش",
  description:
    "محاسبات دقیق چندارزی، گردش‌کار تأیید چندمرحله‌ای، داشبورد آنی و حسابرسی کامل",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
