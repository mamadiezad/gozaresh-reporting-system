"use client";

import { useState } from "react";

import { api, formatMoney, type CalculationResult } from "@/lib/api";

const CURRENCIES = ["IRR", "USD", "EUR", "AED", "GBP", "TRY", "CNY", "JPY", "CHF", "CAD"];

export default function Calculator() {
  const [form, setForm] = useState({
    principal: "1000000000",
    annual_rate_percent: "23.5",
    term_months: 24,
    currency: "IRR",
    convert_to: "",
    compounding_per_year: 12,
    frequency: "monthly",
  });
  const [result, setResult] = useState<CalculationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = { ...form, with_schedule: true };
      if (!form.convert_to || form.convert_to === form.currency) delete payload.convert_to;
      setResult(await api.preview(payload));
    } catch (err) {
      setError(err instanceof Error ? err.message : "محاسبه ناموفق بود");
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-2" style={{ alignItems: "start" }}>
      <form className="card" onSubmit={run}>
        <h2>محاسبه‌گر مالی</h2>

        <div className="field">
          <label htmlFor="principal">مبلغ اصل</label>
          <input
            id="principal"
            value={form.principal}
            onChange={(e) => setForm({ ...form, principal: e.target.value })}
            inputMode="decimal"
            required
          />
        </div>

        <div className="row">
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="currency">ارز</label>
            <select
              id="currency"
              value={form.currency}
              onChange={(e) => setForm({ ...form, currency: e.target.value })}
            >
              {CURRENCIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="convert">تبدیل به</label>
            <select
              id="convert"
              value={form.convert_to}
              onChange={(e) => setForm({ ...form, convert_to: e.target.value })}
            >
              <option value="">بدون تبدیل</option>
              {CURRENCIES.filter((c) => c !== form.currency).map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="row">
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="rate">نرخ سود سالانه (٪)</label>
            <input
              id="rate"
              value={form.annual_rate_percent}
              onChange={(e) => setForm({ ...form, annual_rate_percent: e.target.value })}
              inputMode="decimal"
              required
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="term">مدت (ماه)</label>
            <input
              id="term"
              type="number"
              min={0}
              max={600}
              value={form.term_months}
              onChange={(e) => setForm({ ...form, term_months: Number(e.target.value) })}
              required
            />
          </div>
        </div>

        <div className="row">
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="compounding">تناوب مرکب‌شدن (بار در سال)</label>
            <input
              id="compounding"
              type="number"
              min={1}
              max={365}
              value={form.compounding_per_year}
              onChange={(e) => setForm({ ...form, compounding_per_year: Number(e.target.value) })}
            />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label htmlFor="frequency">تناوب پرداخت</label>
            <select
              id="frequency"
              value={form.frequency}
              onChange={(e) => setForm({ ...form, frequency: e.target.value })}
            >
              <option value="monthly">ماهانه</option>
              <option value="quarterly">سه‌ماهه</option>
              <option value="semiannual">شش‌ماهه</option>
              <option value="annual">سالانه</option>
            </select>
          </div>
        </div>

        {error && <p style={{ color: "var(--danger)", fontSize: "0.85rem" }}>{error}</p>}

        <button className="btn" style={{ width: "100%" }} disabled={busy} type="submit">
          {busy ? "در حال محاسبه…" : "محاسبه"}
        </button>
      </form>

      <div className="stack">
        {result ? (
          <>
            <div className="card">
              <div className="row">
                <h2 style={{ margin: 0 }}>نتیجه</h2>
                <div className="spacer" />
                <span
                  className={`badge ${result.within_sla ? "badge-approved" : "badge-rejected"}`}
                  title={`آستانه ${result.sla_ms} میلی‌ثانیه`}
                >
                  {result.duration_ms.toFixed(2)} ms
                </span>
              </div>

              <table style={{ marginTop: 12 }}>
                <tbody>
                  <Row label="اصل" value={`${formatMoney(result.principal, result.currency)} ${result.currency}`} />
                  <Row label="کل سود" value={`${formatMoney(result.total_interest, result.currency)} ${result.currency}`} />
                  <Row
                    label="مبلغ نهایی"
                    value={`${formatMoney(result.display_total, result.currency)} ${result.currency}`}
                    strong
                  />
                  <Row label="قسط دوره‌ای" value={`${formatMoney(result.periodic_payment, result.currency)} ${result.currency}`} />
                  <Row
                    label="نرخ مؤثر سالانه"
                    value={`${(Number(result.effective_annual_rate) * 100).toFixed(4)}٪`}
                  />
                  {result.amount_in_base && (
                    <Row
                      label={`معادل (نرخ ${Number(result.fx_rate).toLocaleString("fa-IR")})`}
                      value={formatMoney(result.amount_in_base, "IRR")}
                    />
                  )}
                  {result.fx_source && <Row label="منبع نرخ ارز" value={result.fx_source} />}
                </tbody>
              </table>
            </div>

            {result.schedule.length > 0 && (
              <div className="card">
                <h2>جدول اقساط ({result.schedule.length} قسط)</h2>
                <div style={{ maxHeight: 360, overflowY: "auto" }}>
                  <table>
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>سررسید</th>
                        <th>مبلغ قسط</th>
                        <th>اصل</th>
                        <th>سود</th>
                        <th>مانده</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.schedule.map((row) => (
                        <tr key={row.number}>
                          <td>{row.number}</td>
                          <td className="muted">{row.due_date}</td>
                          <td>{formatMoney(row.amount, result.currency)}</td>
                          <td>{formatMoney(row.principal_component, result.currency)}</td>
                          <td>{formatMoney(row.interest_component, result.currency)}</td>
                          <td className="muted">{formatMoney(row.remaining_balance, result.currency)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : (
          <div className="card">
            <p className="muted" style={{ margin: 0 }}>
              مقادیر را وارد کنید و «محاسبه» را بزنید. محاسبات با دقت Decimal تا ۱۶ رقم اعشار و در
              کمتر از ۵۰ میلی‌ثانیه انجام می‌شود.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <tr>
      <td className="muted">{label}</td>
      <td style={{ fontWeight: strong ? 700 : 400, fontVariantNumeric: "tabular-nums" }}>{value}</td>
    </tr>
  );
}
