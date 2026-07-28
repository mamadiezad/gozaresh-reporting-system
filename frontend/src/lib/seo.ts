/**
 * Single source of truth for site identity, canonical URLs and structured data.
 *
 * Set NEXT_PUBLIC_SITE_URL to your real domain before deploying — canonical
 * tags, Open Graph URLs, the sitemap and JSON-LD all derive from it.
 */

export const SITE = {
  url: (process.env.NEXT_PUBLIC_SITE_URL ?? "https://mamadiezad.github.io/gozaresh-reporting-system").replace(/\/$/, ""),
  name: "گزارش | سامانه گزارش‌گیری سازمانی",
  shortName: "گزارش",
  nameEn: "Gozaresh — Enterprise Reporting System",

  title: "سامانه گزارش‌گیری سازمانی | محاسبات چندارزی، گردش‌کار تأیید و حسابرسی",

  description:
    "سامانه متن‌باز گزارش‌گیری سازمانی: محاسبات مالی چندارزی با دقت Decimal و پاسخ زیر ۵۰ میلی‌ثانیه، " +
    "گردش‌کار تأیید سه‌مرحله‌ای با امضای دیجیتال، داشبورد آنی با هشدار اقساط معوق، " +
    "اتصال به سامانه مودیان و درگاه بانکی، و مسیر حسابرسی تغییرناپذیر.",

  descriptionEn:
    "Open-source enterprise reporting platform: multi-currency Decimal calculations under a 50ms SLA, " +
    "a digitally signed three-stage approval workflow, a real-time dashboard, tax and bank integrations, " +
    "and a tamper-evident audit trail.",

  author: "Mohammad",
  authorTelegram: "https://t.me/llllxyz",
  authorHandle: "@llllxyz",
  repo: "https://github.com/mamadiezad/gozaresh-reporting-system",
  locale: "fa_IR",

  keywordsEn: [
    "enterprise reporting system",
    "financial reporting software",
    "open source reporting system",
    "approval workflow engine",
    "multi-stage approval workflow",
    "digital signature workflow",
    "tamper evident audit trail",
    "hash chained audit log",
    "decimal precision financial calculations",
    "multi currency calculation engine",
    "compound interest calculator api",
    "amortisation schedule api",
    "FastAPI financial application",
    "Next.js RTL dashboard",
    "SQLAlchemy decimal precision",
    "RBAC permission system",
    "fintech boilerplate",
    "accounting integration API",
    "Iranian tax authority integration",
    "Moadian API integration",
  ],

  keywords: [
    // Persian — what an Iranian buyer actually searches for
    "سامانه گزارش گیری",
    "سامانه گزارش گیری سازمانی",
    "نرم افزار گزارش گیری سازمان",
    "سیستم گزارش گیری مالی",
    "راه اندازی سامانه گزارش گیری",
    "گردش کار تایید",
    "گردش کار مالی سازمانی",
    "امضای دیجیتال اسناد مالی",
    "سامانه مودیان",
    "اتصال به سامانه مودیان",
    "محاسبه سود مرکب",
    "محاسبه اقساط وام",
    "نرخ تسعیر ارز",
    "داشبورد مدیریتی مالی",
    "هشدار اقساط معوق",
    "مسیر حسابرسی",
    "audit trail فارسی",
    "نرم افزار حسابداری سازمانی",
    "سامانه مالی متن باز",
    // English — developer discovery
    "enterprise reporting system",
    "financial reporting platform",
    "multi-currency calculation engine",
    "decimal precision finance",
    "approval workflow engine",
    "digital signature workflow",
    "tamper evident audit trail",
    "hash chained audit log",
    "FastAPI finance",
    "Next.js dashboard RTL",
    "Iranian tax integration",
    "Moadian API",
    "RBAC fintech",
  ],
} as const;

export function absoluteUrl(path = ""): string {
  return `${SITE.url}${path.startsWith("/") ? path : `/${path}`}`;
}

/** JSON-LD graph: software product + author + org + FAQ, all cross-linked by @id. */
export function structuredData() {
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "SoftwareApplication",
        "@id": absoluteUrl("/#software"),
        name: SITE.nameEn,
        alternateName: SITE.shortName,
        applicationCategory: "BusinessApplication",
        applicationSubCategory: "Financial Reporting",
        operatingSystem: "Web, Linux, Docker",
        description: SITE.descriptionEn,
        inLanguage: ["fa-IR", "en"],
        url: SITE.url,
        codeRepository: SITE.repo,
        license: "https://opensource.org/licenses/MIT",
        softwareVersion: "1.0.0",
        author: { "@id": absoluteUrl("/#author") },
        offers: {
          "@type": "Offer",
          price: "0",
          priceCurrency: "USD",
          availability: "https://schema.org/InStock",
        },
        featureList: [
          "Multi-currency Decimal calculations with 16 decimal places under a 50ms SLA",
          "Three-stage approval workflow with RSA digital signatures",
          "Real-time dashboard with WebSocket alerts for overdue installments",
          "Tax authority, bank gateway and accounting system integrations",
          "Layered security with a hash-chained, tamper-evident audit trail",
        ],
      },
      {
        "@type": "Person",
        "@id": absoluteUrl("/#author"),
        name: SITE.author,
        url: SITE.authorTelegram,
        sameAs: [SITE.authorTelegram, "https://github.com/mamadiezad"],
      },
      {
        "@type": "WebSite",
        "@id": absoluteUrl("/#website"),
        url: SITE.url,
        name: SITE.name,
        description: SITE.description,
        inLanguage: "fa-IR",
        publisher: { "@id": absoluteUrl("/#author") },
      },
      {
        "@type": "FAQPage",
        "@id": absoluteUrl("/#faq"),
        inLanguage: "fa-IR",
        mainEntity: FAQ.map((item) => ({
          "@type": "Question",
          name: item.question,
          acceptedAnswer: { "@type": "Answer", text: item.answer },
        })),
      },
      {
        "@type": "WebPage",
        "@id": absoluteUrl("/en#webpage"),
        url: absoluteUrl("/en"),
        name: SITE.nameEn,
        description: SITE.descriptionEn,
        inLanguage: "en",
        isPartOf: { "@id": absoluteUrl("/#website") },
      },
    ],
  };
}

/** Rendered on the landing page *and* emitted as FAQPage structured data. */
export const FAQ = [
  {
    question: "سامانه گزارش‌گیری سازمانی چیست و چه مشکلی را حل می‌کند؟",
    answer:
      "سامانه گزارش‌گیری سازمانی، ثبت درخواست‌های مالی، محاسبه دقیق مبالغ، مسیر تأیید مدیران و بایگانی حسابرسی را در یک جریان واحد یکپارچه می‌کند. " +
      "به‌جای گردش فایل اکسل و ایمیل، هر گزارش یک شناسه یکتا، جدول اقساط محاسبه‌شده، زنجیره تأیید امضاشده و تاریخچه تغییرات غیرقابل‌دستکاری دارد.",
  },
  {
    question: "چرا محاسبات با Decimal انجام می‌شود و نه اعداد اعشاری معمولی؟",
    answer:
      "نوع float در محاسبات پولی خطای انباشتی ایجاد می‌کند؛ برای مثال ۰٫۱ + ۰٫۲ دقیقاً ۰٫۳ نمی‌شود. " +
      "این سامانه تمام مسیر پولی را با Decimal و گرد کردن بانکی تا ۱۶ رقم اعشار محاسبه می‌کند، به‌طوری که مجموع اجزای اصل اقساط دقیقاً برابر مبلغ اولیه است.",
  },
  {
    question: "گردش‌کار تأیید چند مرحله دارد و امضای دیجیتال چگونه کار می‌کند؟",
    answer:
      "سه مرحله: مدیر مالی، سپس بازرس و در نهایت مدیرعامل. ترتیب مراحل سخت‌گیرانه اعمال می‌شود و پرش از یک مرحله خطا برمی‌گرداند. " +
      "هر تصمیم با کلید RSA-2048 روی هش محتوای گزارش امضا می‌شود؛ بنابراین اگر پس از تأیید کسی مبلغ را تغییر دهد، همه امضاها باطل و این موضوع گزارش می‌شود.",
  },
  {
    question: "آیا امکان اتصال به سامانه مودیان و درگاه بانکی وجود دارد؟",
    answer:
      "بله. سامانه صورتحساب امضاشده را به سامانه مودیان ارسال می‌کند، از درگاه بانک تأییدیه تسویه می‌گیرد و سند حسابداری دوطرفه را به‌صورت JSON یا XML استاندارد با نرم‌افزار حسابداری تبادل می‌کند. " +
      "همه فراخوانی‌ها idempotent هستند و در حالت پیش‌فرض sandbox اجرا می‌شوند.",
  },
  {
    question: "مسیر حسابرسی چگونه از دستکاری جلوگیری می‌کند؟",
    answer:
      "هر رکورد حسابرسی شامل هش رکورد قبلی است و یک زنجیره تشکیل می‌دهد. ویرایش یا حذف هر رکورد تاریخی، زنجیره را می‌شکند و سامانه شماره دقیق رکورد دستکاری‌شده را گزارش می‌کند.",
  },
  {
    question: "آیا پروژه متن‌باز است و می‌توان آن را در سازمان مستقر کرد؟",
    answer:
      "بله، تحت مجوز MIT منتشر شده و با Docker Compose در چند دقیقه بالا می‌آید. بک‌اند با FastAPI و پایتون ۳٫۱۳ و فرانت‌اند با Next.js پیاده‌سازی شده و PostgreSQL برای محیط عملیاتی پشتیبانی می‌شود.",
  },
] as const;
