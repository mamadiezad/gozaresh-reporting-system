import { SITE } from "@/lib/seo";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <p className="site-footer-made">
          made <span aria-hidden="true">❤️</span>
          <span className="sr-only">with love by</span>{" "}
          <a
            href={SITE.authorTelegram}
            target="_blank"
            rel="noopener noreferrer author"
            title="Mohammad on Telegram (@llllxyz)"
          >
            Mohammad
          </a>
        </p>

        <nav className="site-footer-links" aria-label="پیوندهای پاورقی">
          <a href={SITE.repo} target="_blank" rel="noopener noreferrer">
            سورس‌کد
          </a>
          <a href={`${SITE.repo}/blob/main/docs/API.md`} target="_blank" rel="noopener noreferrer">
            مستندات API
          </a>
          <a href={`${SITE.repo}/blob/main/docs/SECURITY.md`} target="_blank" rel="noopener noreferrer">
            مدل امنیتی
          </a>
          <a href={SITE.authorTelegram} target="_blank" rel="noopener noreferrer">
            تماس
          </a>
        </nav>
      </div>
    </footer>
  );
}
