import type { Metadata } from "next";
import Link from "next/link";

import Footer from "@/components/Footer";
import { FAQ, SITE } from "@/lib/seo";

export const metadata: Metadata = {
  title: SITE.title,
  description: SITE.description,
  alternates: { canonical: "/" },
};

const FEATURES = [
  {
    id: "calculations",
    title: "محاسبات دقیق و آنی با پشتیبانی از ارزهای چندگانه",
    body:
      "نرخ تسعیر از منابع معتبر (بانک مرکزی یا API صرافی‌ها) دریافت می‌شود، سود مرکب و اقساط با دقت " +
      "Decimal تا ۱۶ رقم اعشار محاسبه می‌گردد و مبلغ نهایی در کمتر از ۵۰ میلی‌ثانیه نمایش داده می‌شود.",
    points: [
      "هیچ‌جای مسیر پولی از float استفاده نمی‌شود",
      "زنجیره نرخ: بانک مرکزی ← API صرافی ← آخرین نرخ معتبر",
      "p99 اندازه‌گیری‌شده: ۱٫۷ میلی‌ثانیه",
    ],
  },
  {
    id: "workflow",
    title: "گردش‌کار تأیید چندمرحله‌ای",
    body:
      "هر درخواست پس از ثبت، به‌صورت خودکار برای تأیید مدیر مالی، سپس بازرس و در نهایت مدیرعامل ارسال " +
      "می‌شود و در هر مرحله لاگ کامل و امضای دیجیتال ثبت می‌گردد.",
    points: [
      "ترتیب مراحل سخت‌گیرانه اعمال می‌شود",
      "امضای RSA-2048 روی هش محتوای گزارش",
      "تغییر مبلغ پس از تأیید، امضاها را باطل می‌کند",
    ],
  },
  {
    id: "dashboard",
    title: "داشبورد هوشمند و هشدارهای آنی",
    body:
      "نمایش وضعیت گزارش‌ها به‌صورت لحظه‌ای با نمودارهای تعاملی، هشدار برای اقساط معوق، تشخیص " +
      "تراکنش‌های خارج از بازه مجاز و ارسال نوتیفیکیشن از طریق ایمیل، پیامک و WebSocket.",
    points: [
      "تشخیص ناهنجاری آماری مبتنی بر MAD",
      "هشدار گردش‌کارهای متوقف‌شده",
      "هشدارهای تکراری حذف می‌شوند",
    ],
  },
  {
    id: "integrations",
    title: "اتصال یکپارچه به سامانه‌های مالیاتی و بانکی",
    body:
      "ارسال خودکار گزارش‌ها به سامانه مودیان، دریافت تأییدیه از درگاه بانک برای تسویه‌ها و تبادل داده " +
      "با نرم‌افزارهای حسابداری از طریق REST API یا فایل‌های XML/JSON استاندارد.",
    points: [
      "همه فراخوانی‌ها idempotent هستند",
      "اعتبارسنجی IBAN با الگوریتم mod-97",
      "تلاش مجدد با backoff نمایی",
    ],
  },
  {
    id: "security",
    title: "امنیت لایه‌ای و حسابرسی کامل",
    body:
      "احراز هویت JWT، رمزنگاری Argon2id، کنترل دسترسی نقش‌محور، رمزگذاری سطح فیلد برای اطلاعات هویتی " +
      "و مسیر حسابرسی زنجیره‌ای که هرگونه دستکاری در تاریخچه را آشکار می‌کند.",
    points: [
      "زنجیره هش: H(هش قبلی ‖ محتوا)",
      "شماره دقیق رکورد دستکاری‌شده گزارش می‌شود",
      "پاک‌سازی خودکار گذرواژه و اطلاعات حساس از لاگ",
    ],
  },
];

const STATS = [
  { value: "‎<۵۰ms", label: "زمان پاسخ محاسبات" },
  { value: "۱۶", label: "رقم اعشار دقت" },
  { value: "۵۱", label: "endpoint آماده" },
  { value: "۱۱۵", label: "تست خودکار" },
];

export default function LandingPage() {
  return (
    <div className="landing">
      <header className="landing-hero">
        <p className="landing-eyebrow">متن‌باز · MIT · آماده استقرار با Docker</p>

        <h1>سامانه گزارش‌گیری سازمانی</h1>

        <p className="landing-lede">
          راهکار کامل توسعه و راه‌اندازی سامانه‌های گزارش‌گیری در سازمان‌ها: محاسبات مالی چندارزی با
          دقت Decimal، گردش‌کار تأیید چندمرحله‌ای با امضای دیجیتال، داشبورد آنی و مسیر حسابرسی
          تغییرناپذیر.
        </p>

        <div className="landing-cta">
          <Link className="btn" href="/app">
            ورود به داشبورد
          </Link>
          <a className="btn ghost" href={SITE.repo} target="_blank" rel="noopener noreferrer">
            مشاهده سورس‌کد
          </a>
        </div>

        <dl className="landing-stats">
          {STATS.map((stat) => (
            <div key={stat.label}>
              <dt>{stat.label}</dt>
              <dd>{stat.value}</dd>
            </div>
          ))}
        </dl>
      </header>

      <main>
        <section aria-labelledby="features-heading" className="landing-section">
          <h2 id="features-heading">قابلیت‌های سامانه</h2>

          <div className="landing-features">
            {FEATURES.map((feature, index) => (
              <article key={feature.id} id={feature.id}>
                <span className="landing-feature-num" aria-hidden="true">
                  {index + 1}
                </span>
                <h3>{feature.title}</h3>
                <p>{feature.body}</p>
                <ul>
                  {feature.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>

        <section aria-labelledby="stack-heading" className="landing-section">
          <h2 id="stack-heading">پشته فناوری</h2>
          <p className="landing-section-lede">
            بک‌اند با FastAPI و پایتون ۳٫۱۳، فرانت‌اند با Next.js 15 و React 19، پایگاه‌داده
            PostgreSQL برای محیط عملیاتی، و استقرار با Docker Compose.
          </p>
          <ul className="landing-chips">
            {[
              "FastAPI",
              "Python 3.13",
              "SQLAlchemy 2.0",
              "PostgreSQL",
              "Next.js 15",
              "React 19",
              "TypeScript",
              "WebSocket",
              "Docker",
              "Argon2id",
              "RSA-PSS",
              "JWT",
            ].map((chip) => (
              <li key={chip}>{chip}</li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="faq-heading" className="landing-section">
          <h2 id="faq-heading">پرسش‌های متداول</h2>

          <div className="landing-faq">
            {FAQ.map((item) => (
              <details key={item.question}>
                <summary>
                  <h3>{item.question}</h3>
                </summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
