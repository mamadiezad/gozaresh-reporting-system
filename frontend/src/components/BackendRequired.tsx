import Link from "next/link";

import { SITE } from "@/lib/seo";

/**
 * Shown instead of the dashboard on the statically exported build.
 *
 * GitHub Pages serves static files only — there is no backend for a visitor to
 * talk to, so rendering the login form there would guarantee a "Failed to
 * fetch". This page states that plainly and gives the two commands needed to
 * run the real thing locally.
 */
export default function BackendRequired() {
  return (
    <div className="landing" style={{ maxWidth: 820 }}>
      <header className="landing-hero" style={{ paddingBottom: 28 }}>
        <p className="landing-eyebrow">اجرای محلی لازم است</p>
        <h1 style={{ fontSize: "clamp(1.5rem, 4vw, 2.1rem)" }}>
          داشبورد به بک‌اند نیاز دارد
        </h1>
        <p className="landing-lede">
          این صفحه روی GitHub Pages میزبانی می‌شود که فقط فایل‌های استاتیک را سرو می‌کند و
          بک‌اندی برای پاسخ‌گویی وجود ندارد. برای دیدن داشبورد واقعی — با محاسبات، گردش‌کار
          تأیید و مسیر حسابرسی — پروژه را در چند دقیقه روی سیستم خودتان بالا بیاورید.
        </p>
      </header>

      <main>
        <section className="landing-section" style={{ paddingTop: 32 }}>
          <h2>راه‌اندازی با Docker</h2>
          <pre className="code-block" dir="ltr">
            <code>{`git clone ${SITE.repo}.git
cd gozaresh-reporting-system
docker compose up --build

# داشبورد → http://localhost:3000
# مستندات → http://localhost:8000/docs`}</code>
          </pre>

          <h2 style={{ marginTop: 32 }}>حساب‌های نمونه</h2>
          <p className="landing-section-lede" style={{ marginBottom: 12 }}>
            گذرواژه‌ی همه: <code className="inline-code" dir="ltr">DemoPass!2024</code>
          </p>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>کاربر</th>
                  <th>نقش</th>
                  <th>دسترسی</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["alice", "درخواست‌دهنده", "ثبت و ارسال گزارش"],
                  ["bob", "مدیر مالی", "تأیید مرحله اول"],
                  ["carol", "بازرس", "تأیید مرحله دوم و حسابرسی"],
                  ["dave", "مدیرعامل", "تأیید نهایی"],
                  ["erin", "حسابرس", "بررسی زنجیره حسابرسی"],
                ].map(([user, role, access]) => (
                  <tr key={user}>
                    <td dir="ltr" className="mono">{user}</td>
                    <td>{role}</td>
                    <td className="muted">{access}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="landing-cta" style={{ justifyContent: "flex-start", marginTop: 32 }}>
            <a className="btn" href={SITE.repo} target="_blank" rel="noopener noreferrer">
              مشاهده سورس‌کد
            </a>
            <a
              className="btn ghost"
              href={`${SITE.repo}/blob/main/docs/API.md`}
              target="_blank"
              rel="noopener noreferrer"
            >
              مستندات API
            </a>
            <Link className="btn ghost" href="/">
              بازگشت به صفحه اصلی
            </Link>
          </div>
        </section>
      </main>
    </div>
  );
}
