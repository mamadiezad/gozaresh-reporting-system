import type { Metadata } from "next";
import Link from "next/link";

import { SITE, absoluteUrl } from "@/lib/seo";
import { FAQ_EN, FEATURES_EN } from "@/lib/seo.en";

export const metadata: Metadata = {
  title: {
    absolute: "Enterprise Reporting System — Multi-Currency, Signed Approvals, Audit Trail",
  },
  description: SITE.descriptionEn,
  keywords: [...SITE.keywordsEn],
  alternates: {
    canonical: "/en",
    languages: { "fa-IR": "/", en: "/en", "x-default": "/" },
  },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: absoluteUrl("/en"),
    siteName: SITE.nameEn,
    title: "Enterprise Reporting System — Multi-Currency, Signed Approvals, Audit Trail",
    description: SITE.descriptionEn,
    images: [{ url: absoluteUrl("/og.png"), width: 1200, height: 630, alt: SITE.nameEn }],
  },
};

const STATS = [
  { value: "<50ms", label: "Calculation response" },
  { value: "16", label: "Decimal places" },
  { value: "51", label: "REST endpoints" },
  { value: "115", label: "Automated tests" },
];

export default function EnglishLanding() {
  return (
    <div className="landing" dir="ltr" lang="en" style={{ textAlign: "left" }}>
      <header className="landing-hero">
        <p className="landing-eyebrow">Open source · MIT · Docker-ready</p>

        <h1>Enterprise Reporting System</h1>

        <p className="landing-lede">
          A production-grade reference implementation for organisational financial reporting:
          multi-currency Decimal calculations under a 50&nbsp;ms SLA, a digitally signed
          three-stage approval workflow, a real-time dashboard, tax and banking integrations,
          and a tamper-evident audit trail.
        </p>

        <div className="landing-cta">
          <a className="btn" href={SITE.repo} target="_blank" rel="noopener noreferrer">
            View on GitHub
          </a>
          <Link className="btn ghost" href="/">
            نسخه فارسی
          </Link>
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
        <section aria-labelledby="features-en" className="landing-section">
          <h2 id="features-en">Core capabilities</h2>

          <div className="landing-features">
            {FEATURES_EN.map((feature, index) => (
              <article key={feature.id} id={`en-${feature.id}`}>
                <span
                  className="landing-feature-num"
                  aria-hidden="true"
                  style={{ insetInlineEnd: "auto", insetInlineStart: 20 }}
                >
                  {index + 1}
                </span>
                <h3 style={{ paddingInlineEnd: 0, paddingInlineStart: 44 }}>{feature.title}</h3>
                <p>{feature.body}</p>
                <ul style={{ paddingInlineStart: 18 }}>
                  {feature.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </section>

        <section aria-labelledby="who-en" className="landing-section">
          <h2 id="who-en">Who is this for?</h2>
          <div className="landing-features">
            <article>
              <h3 style={{ paddingInlineEnd: 0 }}>Engineering teams</h3>
              <p>
                A worked example of financial correctness in Python: exact Decimal arithmetic,
                a custom SQLAlchemy column type that survives SQLite&apos;s float coercion,
                RSA-signed state transitions, and a hash-chained audit log — all covered by
                115 tests at 84% coverage.
              </p>
            </article>
            <article>
              <h3 style={{ paddingInlineEnd: 0 }}>Organisations &amp; buyers</h3>
              <p>
                A deployable starting point for internal reporting: replace spreadsheet and
                email approval chains with signed, auditable workflows that integrate with
                your tax authority, bank gateway and accounting software.
              </p>
            </article>
          </div>
        </section>

        <section aria-labelledby="stack-en" className="landing-section">
          <h2 id="stack-en">Technology stack</h2>
          <p className="landing-section-lede">
            FastAPI on Python 3.13, SQLAlchemy 2.0 with PostgreSQL, Next.js 15 with React 19
            and TypeScript, real-time updates over WebSocket, containerised with Docker Compose.
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

        <section aria-labelledby="faq-en" className="landing-section">
          <h2 id="faq-en">Frequently asked questions</h2>
          <div className="landing-faq">
            {FAQ_EN.map((item) => (
              <details key={item.question}>
                <summary>
                  <h3>{item.question}</h3>
                </summary>
                <p style={{ paddingInlineStart: 24 }}>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="site-footer-inner">
          <p className="site-footer-made">
            made <span aria-hidden="true">❤️</span>{" "}
            <a href={SITE.authorTelegram} target="_blank" rel="noopener noreferrer author">
              Mohammad
            </a>
          </p>
          <nav className="site-footer-links" aria-label="Footer links">
            <a href={SITE.repo} target="_blank" rel="noopener noreferrer">
              Source
            </a>
            <a href={`${SITE.repo}/blob/main/docs/API.md`} target="_blank" rel="noopener noreferrer">
              API docs
            </a>
            <a href={`${SITE.repo}/blob/main/docs/SECURITY.md`} target="_blank" rel="noopener noreferrer">
              Security
            </a>
            <Link href="/">فارسی</Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
