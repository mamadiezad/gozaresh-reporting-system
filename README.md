<div dir="rtl">

# گزارش — سامانه گزارش‌گیری سازمانی

سامانه‌ی مرجع (reference implementation) برای توسعه و راه‌اندازی سامانه‌های گزارش‌گیری در سازمان‌ها؛ با محاسبات دقیق چندارزی، گردش‌کار تأیید چندمرحله‌ای همراه با امضای دیجیتال، داشبورد آنی، اتصال به سامانه‌های مالیاتی و بانکی، و مسیر حسابرسی تغییرناپذیر.

</div>

[![CI](https://github.com/mamadiezad/gozaresh-reporting-system/actions/workflows/ci.yml/badge.svg)](https://github.com/mamadiezad/gozaresh-reporting-system/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.13-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.140-009688)
![Next.js](https://img.shields.io/badge/Next.js-15.5-black)
![Tests](https://img.shields.io/badge/tests-115%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-84%25-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)
[![Telegram](https://img.shields.io/badge/Telegram-%40llllxyz-2CA5E0?logo=telegram&logoColor=white)](https://t.me/llllxyz)

---

## فهرست

- [قابلیت‌های اصلی](#قابلیتهای-اصلی)
- [راه‌اندازی سریع](#راهاندازی-سریع)
- [معماری](#معماری)
- [مستندات API](#مستندات-api)
- [تصمیمات فنی مهم](#تصمیمات-فنی-مهم)
- [تست‌ها](#تستها)
- [استقرار در محیط عملیاتی](#استقرار-در-محیط-عملیاتی)
- [بهینه‌سازی موتور جستجو](#بهینهسازی-موتور-جستجو-seo)
- [توسعه‌دهنده](#توسعهدهنده)

---

<div dir="rtl">

## قابلیت‌های اصلی

### ۱. محاسبات دقیق و آنی با پشتیبانی از ارزهای چندگانه

سیستم نرخ تسعیر را از منابع معتبر دریافت می‌کند، سود مرکب و اقساط را با دقت `Decimal` (۱۶ رقم اعشار) محاسبه می‌کند و مبلغ نهایی را در **کمتر از ۵۰ میلی‌ثانیه** برمی‌گرداند.

| موضوع | پیاده‌سازی |
|---|---|
| دقت | `Decimal` با ۱۶ رقم اعشار و گرد کردن بانکی (`ROUND_HALF_EVEN`) — هیچ‌جا از `float` استفاده نمی‌شود |
| منابع نرخ | زنجیره‌ی چندلایه: بانک مرکزی ← API صرافی ← آخرین نرخ معتبر ذخیره‌شده |
| کش | کش TTL درون‌فرایندی (پیش‌فرض ۳۰۰ ثانیه) برای ماندن زیر آستانه SLA |
| سنجش | زمان هر محاسبه در هدر `X-Calc-Duration-Ms` و در پاسخ برگردانده می‌شود |
| نتیجه واقعی | p99 اندازه‌گیری‌شده: **۱٫۷ میلی‌ثانیه** برای وام ۶۰ ماهه (۲۹ برابر سریع‌تر از الزام) |

نتیجه‌ی `GET /api/v1/calculations/benchmark?iterations=300`:

</div>

```json
{
  "iterations": 300, "sla_ms": 50.0,
  "p50_ms": 1.04, "p95_ms": 1.16, "p99_ms": 1.71, "max_ms": 2.18,
  "sla_met_ratio": 1.0
}
```

<div dir="rtl">

### ۲. گردش‌کار تأیید چندمرحله‌ای

هر درخواست پس از ثبت، به‌صورت خودکار برای **مدیر مالی ← بازرس ← مدیرعامل** ارسال می‌شود و در هر مرحله لاگ کامل و امضای دیجیتال ثبت می‌گردد.

- ترتیب مراحل به‌صورت سخت‌گیرانه اعمال می‌شود؛ پرش از یک مرحله خطای `409` برمی‌گرداند.
- هر تصمیم با کلید **RSA-2048 (RSA-PSS/SHA-256)** روی یک payload متعارف (canonical) امضا می‌شود.
- امضا شامل هش محتوای گزارش است؛ بنابراین **هر تغییر بعدی در مبلغ، امضاها را باطل می‌کند** و در `GET /reports/{id}/signatures` گزارش می‌شود.
- رد شدن در هر مرحله، مراحل بعدی را `skipped` کرده و گردش‌کار را متوقف می‌کند.

### ۳. داشبورد هوشمند و هشدارهای آنی

- نمودارهای تعاملی (Recharts): وضعیت گزارش‌ها، روند ۱۲ ماهه، توزیع ارزی، گلوگاه مراحل تأیید.
- تشخیص خودکار: **اقساط معوق**، **تراکنش خارج از بازه مجاز**، **ناهنجاری آماری** (z-score اصلاح‌شده مبتنی بر MAD)، و **گردش‌کارهای متوقف‌شده**.
- ارسال نوتیفیکیشن از سه کانال: **ایمیل، پیامک و WebSocket**.
- هشدارها `dedupe key` دارند؛ اسکن مکرر، هشدار تکراری تولید نمی‌کند.

### ۴. اتصال یکپارچه به سامانه‌های مالیاتی و بانکی

| مقصد | عملیات |
|---|---|
| سامانه مودیان | ساخت و ارسال صورتحساب امضاشده، استعلام وضعیت |
| درگاه بانک | درخواست تسویه، دریافت تأییدیه، اعتبارسنجی IBAN با الگوریتم mod-97 |
| نرم‌افزار حسابداری | سند حسابداری دوطرفه به‌صورت REST/JSON و **XML استاندارد** (خروجی و ورودی) |

همه‌ی فراخوانی‌ها **idempotent** هستند (کلید مبتنی بر هش payload)، با **backoff نمایی** تلاش مجدد می‌کنند و در `integration_logs` ثبت می‌شوند.

### ۵. امنیت لایه‌ای و حسابرسی کامل

| لایه | پیاده‌سازی |
|---|---|
| احراز هویت | JWT (access + refresh)، کلید API برای سرویس‌ها |
| گذرواژه | **Argon2id** (۶۴MB حافظه، ۳ دور) + سیاست پیچیدگی |
| قفل حساب | پس از ۵ تلاش ناموفق، ۱۵ دقیقه قفل — لاگ آن حتی هنگام خطای HTTP ثبت می‌شود |
| مجوزها | RBAC با ۷ نقش و ماتریس دسترسی صریح |
| رمزنگاری داده | رمزگذاری سطح فیلد (Fernet) برای PII + **blind index** برای جست‌وجوی دقیق |
| مسیر حسابرسی | زنجیره‌ی هش‌شده: هر رکورد `H(hash قبلی ‖ محتوا)` — حذف یا ویرایش تاریخچه بلافاصله شناسایی می‌شود |
| پاک‌سازی | گذرواژه‌ها، توکن‌ها و کدهای ملی پیش از ثبت در لاگ حسابرسی حذف می‌شوند |
| هدرهای امنیتی | CSP، HSTS، `X-Frame-Options: DENY`، `nosniff`، محدودیت نرخ درخواست |

`GET /api/v1/audit/verify` کل زنجیره را بازمحاسبه می‌کند و **شماره دقیق رکورد دستکاری‌شده** را برمی‌گرداند.

---

## راه‌اندازی سریع

### گزینه ۱: Docker (توصیه‌شده)

</div>

```bash
git clone https://github.com/mamadiezad/gozaresh-reporting-system.git gozaresh
cd gozaresh
docker compose up --build

# داشبورد:  http://localhost:3000
# مستندات:  http://localhost:8000/docs
```

<div dir="rtl">

### گزینه ۲: اجرای محلی

</div>

```bash
# ---------- بک‌اند ----------
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                     # SECRET_KEY را عوض کنید

python scripts/seed.py --reset           # ساخت داده‌های نمونه
uvicorn app.main:app --reload            # http://localhost:8000/docs

# ---------- فرانت‌اند (ترمینال دوم) ----------
cd frontend
npm install
cp .env.example .env.local               # NEXT_PUBLIC_SITE_URL را تنظیم کنید
npm run dev                              # http://localhost:3000
```

<div dir="rtl">

### حساب‌های نمونه

گذرواژه‌ی همه: `DemoPass!2024`

| کاربر | نقش | دسترسی |
|---|---|---|
| `alice` | درخواست‌دهنده | ثبت و ارسال گزارش |
| `bob` | مدیر مالی | تأیید مرحله اول |
| `carol` | بازرس | تأیید مرحله دوم + حسابرسی |
| `dave` | مدیرعامل | تأیید نهایی |
| `erin` | حسابرس | فقط خواندن + بررسی زنجیره |
| `root` | مدیر سیستم | دسترسی کامل |

---

## معماری

</div>

```
gozaresh/
├── backend/
│   ├── app/
│   │   ├── core/              # پیکربندی، دیتابیس، امنیت، امضای دیجیتال
│   │   │   ├── config.py      # تنظیمات مبتنی بر متغیر محیطی
│   │   │   ├── security.py    # Argon2، JWT، رمزنگاری فیلد، RBAC
│   │   │   └── signing.py     # RSA-PSS + زنجیره هش
│   │   ├── models/            # مدل‌های SQLAlchemy 2.0
│   │   │   └── types.py       # نوع Money — دقت دقیق در همه بک‌اندها
│   │   ├── schemas/           # مدل‌های Pydantic v2
│   │   ├── services/
│   │   │   ├── calculator.py  # موتور مالی (Decimal خالص)
│   │   │   ├── fx.py          # نرخ ارز چندمنبعی با fallback
│   │   │   ├── workflow.py    # گردش‌کار سه‌مرحله‌ای امضاشده
│   │   │   ├── alerts.py      # موتور تشخیص و هشدار
│   │   │   ├── audit.py       # مسیر حسابرسی زنجیره‌ای
│   │   │   ├── dashboard.py   # تجمیع داده‌های داشبورد
│   │   │   └── notifier.py    # ایمیل / پیامک / WebSocket
│   │   ├── integrations/      # مودیان، بانک، حسابداری
│   │   ├── api/v1/            # ۵۱ endpoint
│   │   └── main.py            # اپلیکیشن + middleware + زمان‌بند
│   ├── tests/                 # ۱۱۵ تست (پوشش ۸۴٪)
│   └── scripts/seed.py
├── frontend/                  # Next.js 15 + React 19 (RTL فارسی)
│   ├── public/og.png          # تصویر Open Graph (متن فارسی شکل‌دهی‌شده)
│   └── src/
│       ├── app/
│       │   ├── page.tsx       # صفحه فرود — استاتیک و بهینه برای SEO
│       │   ├── app/page.tsx   # داشبورد (پشت احراز هویت، noindex)
│       │   ├── sitemap.ts     # نقشه سایت خودکار
│       │   ├── robots.ts      # قوانین خزش
│       │   └── manifest.ts    # PWA manifest
│       ├── components/        # داشبورد، محاسبه‌گر، گردش‌کار، حسابرسی، پاورقی
│       └── lib/
│           ├── api.ts         # کلاینت تایپ‌شده + WebSocket
│           └── seo.ts         # متادیتا، کلیدواژه‌ها و JSON-LD
├── scripts/smoke-test.sh      # ۲۴ بررسی end-to-end
├── docs/                      # مستندات API و مدل امنیتی
└── .github/workflows/ci.yml
```

<div dir="rtl">

**جریان یک گزارش:**

</div>

```
ثبت ──> محاسبه (Decimal، <50ms) ──> تولید اقساط ──> بررسی بازه مجاز
                                                          │
                                                          ▼
                            ┌───────── ارسال برای تأیید ─────────┐
                            ▼                                     │
                   مدیر مالی ──امضا──> بازرس ──امضا──> مدیرعامل ──امضا──> تأییدشده
                            │              │              │                 │
                            └──── رد ──────┴──── رد ──────┘                 ▼
                                     │                          مودیان + بانک + حسابداری
                                     ▼                                      │
                                  ردشده                                     ▼
                                                              همه‌چیز در مسیر حسابرسی ثبت می‌شود
```

<div dir="rtl">

---

## مستندات API

پس از اجرا، مستندات تعاملی در `/docs` (Swagger) و `/redoc` در دسترس است. ۵۱ endpoint در ۷ گروه:

| گروه | نمونه endpoint |
|---|---|
| `auth` | `POST /auth/login`، `POST /auth/refresh`، `GET /auth/me` |
| `calculations` | `POST /calculations/preview`، `GET /calculations/rates/{base}/{quote}`، `GET /calculations/benchmark` |
| `reports` | `POST /reports`، `POST /reports/{id}/submit`، `POST /reports/{id}/decision`، `GET /reports/{id}/signatures` |
| `dashboard` | `GET /dashboard/overview`، `WS /ws/dashboard` |
| `alerts` | `GET /alerts`، `POST /alerts/scan`، `POST /alerts/{id}/acknowledge` |
| `audit` | `GET /audit/logs`، `GET /audit/verify`، `GET /audit/export` |
| `integrations` | `POST /integrations/moadian/{id}/submit`، `POST /integrations/bank/{id}/settle` |

جزئیات کامل: [`docs/API.md`](docs/API.md) · مدل امنیتی: [`docs/SECURITY.md`](docs/SECURITY.md)

---

## تصمیمات فنی مهم

در حین توسعه چند مشکل واقعی شناسایی و برطرف شد که ارزش مستندسازی دارند:

### دقت اعشاری در SQLite

SQLite نوع `NUMERIC` را به‌صورت `double` ذخیره می‌کند. مقدار
`12500000000.1234567890123456` هنگام خواندن به `12500000000.1234569549560547`
تبدیل می‌شد — یعنی تضمین ۱۶ رقم اعشار **بی‌صدا نقض** و امضاهای دیجیتال باطل می‌شدند.

**راه‌حل:** نوع سفارشی [`Money`](backend/app/models/types.py) که روی SQLite مقدار را
به‌صورت رشته‌ی صفرپرشده و offset‌دار ذخیره می‌کند (تا `ORDER BY` همچنان عددی بماند)
و روی PostgreSQL از `NUMERIC(38,16)` بومی استفاده می‌کند. تست رگرسیون:
`tests/test_calculator.py::TestStoragePrecision`.

### سرریز کانتکست Decimal

`quantize()` با کانتکست پیش‌فرض ۲۸ رقمی اجرا می‌شد؛ هر مبلغ ریالی بالای ۱۲ رقم
(کاملاً معمول) خطای `InvalidOperation` می‌داد. اکنون همه‌ی عملیات پولی داخل
`money_context` با دقت ۶۰ رقم اجرا می‌شوند.

### از دست رفتن لاگ در ورودهای ناموفق

استثنای HTTP باعث `rollback` سشن می‌شد و رکورد «ورود ناموفق» و شمارنده‌ی قفل حساب
از بین می‌رفت — یک نقص امنیتی جدی. اکنون پیش از پرتاب استثنا `commit` انجام می‌شود.

### نرمال‌سازی زمان و اعشار برای امضا

SQLite اطلاعات منطقه‌ی زمانی را حذف می‌کند و مقیاس Decimal را تغییر می‌دهد؛
`Decimal("125")` و `Decimal("125.0000000000000000")` رشته‌های متفاوتی تولید می‌کنند.
هر دو در payload امضا نرمال‌سازی می‌شوند تا امضا پس از بارگذاری مجدد از دیتابیس
همچنان معتبر بماند. تست رگرسیون: `TestSignaturePersistence`.

---

## تست‌ها

</div>

```bash
cd backend

pytest -q                                  # ۱۱۵ تست
pytest -q --cov=app --cov-report=term      # با گزارش پوشش
python -m ruff check app tests scripts     # لینت
python -m ruff format --check app tests    # بررسی فرمت

# تست end-to-end روی سرور در حال اجرا
bash ../scripts/smoke-test.sh http://localhost:8000
```

<div dir="rtl">

| مجموعه | تعداد | پوشش |
|---|---|---|
| `test_calculator.py` | ۳۰ | دقت Decimal، SLA، گرد کردن ارزی، ماندگاری در دیتابیس |
| `test_workflow.py` | ۱۵ | ترتیب مراحل، امضای دیجیتال، تشخیص دستکاری |
| `test_audit.py` | ۳۰ | Argon2، رمزنگاری، RBAC، زنجیره هش، قفل حساب |
| `test_fx_and_alerts.py` | ۲۴ | نرخ ارز، تبدیل، هشدارها، داشبورد |
| `test_integrations.py` | ۱۶ | مودیان، بانک، حسابداری، IBAN، idempotency |

اسکریپت `smoke-test.sh` نیز ۲۴ بررسی end-to-end روی یک سرور واقعی انجام می‌دهد.

---

## استقرار در محیط عملیاتی

**پیش از استقرار حتماً:**

1. `SECRET_KEY` را با یک مقدار تصادفی بلند جایگزین کنید (`openssl rand -hex 32`).
2. `DATABASE_URL` را به PostgreSQL تغییر دهید — SQLite فقط برای توسعه است.
3. `ENV=prod` و `DEBUG=false` را تنظیم کنید (HSTS و پنهان‌سازی خطاها فعال می‌شود).
4. `FX_OFFLINE_MODE=false` و آدرس واقعی منابع نرخ ارز را وارد کنید.
5. `INTEGRATIONS_SANDBOX=false` و اعتبارنامه‌های واقعی مودیان/بانک را تنظیم کنید.
6. `NOTIFICATIONS_DRY_RUN=false` و اطلاعات SMTP و درگاه پیامک را وارد کنید.
7. کلیدهای امضا (`KEYSTORE_DIR`) را به یک **HSM یا KMS** منتقل کنید؛ کلیدهای فایلی فقط برای نمونه‌سازی مناسب‌اند.
8. محدودیت نرخ درخواست را به Redis منتقل کنید تا در حالت چندنمونه‌ای درست کار کند.
9. برای مهاجرت‌های شِما، Alembic را اضافه کنید (`Base.metadata.create_all` فقط برای شروع سریع است).

</div>

```bash
# نمونه‌ی متغیرهای محیطی برای production
ENV=prod
DEBUG=false
SECRET_KEY=$(openssl rand -hex 32)
DATABASE_URL=postgresql+psycopg://user:pass@db-host:5432/gozaresh
FX_OFFLINE_MODE=false
INTEGRATIONS_SANDBOX=false
NOTIFICATIONS_DRY_RUN=false
ALLOWED_ORIGINS=https://reports.your-org.ir
```

<div dir="rtl">

---

## بهینه‌سازی موتور جستجو (SEO)

صفحه‌ی فرود پروژه به‌صورت **استاتیک** رندر می‌شود (۳٫۵ کیلوبایت) و کاملاً برای موتورهای جستجو قابل خزش است:

| مورد | پیاده‌سازی |
|---|---|
| متادیتا | عنوان، توضیحات و کلیدواژه‌های فارسی و انگلیسی از `src/lib/seo.ts` |
| داده ساختاریافته | JSON-LD شامل `SoftwareApplication`، `Person`، `WebSite` و `FAQPage` |
| نقشه سایت | `/sitemap.xml` تولید خودکار |
| robots | `/robots.txt` — داشبورد (`/app`) از ایندکس خارج است تا امتیاز صفحه اصلی رقیق نشود |
| Open Graph | تصویر ۱۲۰۰×۶۳۰ با شکل‌دهی صحیح متن فارسی |
| ساختار محتوا | یک `h1`، سرفصل‌های منظم `h2`/`h3`، و بخش پرسش‌های متداول در HTML |
| زبان و جهت | `lang="fa"` و `dir="rtl"` |
| PWA | `manifest.webmanifest` و آیکون SVG |

**پیش از انتشار عمومی:**

1. مقدار `NEXT_PUBLIC_SITE_URL` را در `.env.local` روی دامنه واقعی تنظیم کنید — تگ canonical، Open Graph، sitemap و JSON-LD همگی از آن مشتق می‌شوند.
2. دامنه را در [Google Search Console](https://search.google.com/search-console) ثبت و `sitemap.xml` را معرفی کنید.
3. تصویر Open Graph را با [ابزار اعتبارسنجی](https://cards-dev.twitter.com/validator) بررسی کنید.
4. اگر متن صفحه فرود را تغییر دادید، تصویر OG را دوباره بسازید:

</div>

```bash
python scripts/generate-og-image.py --font-dir /path/to/vazirmatn/ttf
```

<div dir="rtl">

> تصویر OG با Pillow و کتابخانه raqm ساخته می‌شود، نه با `next/og`. موتور Satori در
> `next/og` قابلیت شکل‌دهی متن عربی/فارسی ندارد و حروف را جدا و برعکس رندر می‌کند.

---

## توسعه‌دهنده

ساخته‌شده با ❤️ توسط **[Mohammad](https://t.me/llllxyz)** — تلگرام: [@llllxyz](https://t.me/llllxyz)

اگر این پروژه برایتان مفید بود، یک ⭐ روی گیت‌هاب دلگرم‌کننده است.

</div>

<div dir="rtl">

---

## مجوز

MIT — جزئیات در [`LICENSE`](LICENSE).

> **توجه:** اتصال به سامانه مودیان و درگاه بانکی به‌صورت پیش‌فرض در حالت **sandbox**
> اجرا می‌شود و پاسخ‌ها شبیه‌سازی‌شده هستند. برای استفاده‌ی واقعی باید اعتبارنامه‌های
> رسمی دریافت و مطابق آخرین مستندات هر سازمان، schema پیام‌ها به‌روزرسانی شود.

</div>
