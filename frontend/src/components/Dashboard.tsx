"use client";

import { useCallback, useEffect, useState } from "react";

import { CurrencyBars, StatusPie, TrendChart } from "@/components/Charts";
import {
  api,
  formatDate,
  formatMoney,
  SEVERITY_LABELS,
  STATUS_LABELS,
  type Alert,
  type Kpis,
  type Report,
} from "@/lib/api";

interface Props {
  live: boolean;
  refreshToken: number;
}

export default function Dashboard({ live, refreshToken }: Props) {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [statusData, setStatusData] = useState<Array<{ status: string; count: number }>>([]);
  const [currencyData, setCurrencyData] = useState<
    Array<{ currency: string; count: number; total_in_base: string }>
  >([]);
  const [trendData, setTrendData] = useState<
    Array<{ month: string; count: number; approved: number; value_base: string }>
  >([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [recent, setRecent] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [k, s, c, t, a, r] = await Promise.all([
        api.kpis(),
        api.chartStatus(),
        api.chartCurrency(),
        api.chartTrend(12),
        api.alerts({ acknowledged: "false", limit: "6" }),
        api.reports({ page_size: 6 }),
      ]);
      setKpis(k);
      setStatusData(s);
      setCurrencyData(c);
      setTrendData(t);
      setAlerts(a);
      setRecent(r.items);
    } catch {
      /* surfaced by the parent toast stack */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  if (loading) return <p className="muted">در حال بارگذاری…</p>;

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="grid grid-kpi">
        <Kpi label="کل گزارش‌ها" value={kpis?.total_reports ?? 0} sub={`${kpis?.pending ?? 0} در جریان`} />
        <Kpi
          label="نرخ تأیید"
          value={`${Number(kpis?.approval_rate_percent ?? 0).toFixed(1)}٪`}
          sub={`${kpis?.approved ?? 0} تأیید / ${kpis?.rejected ?? 0} رد`}
        />
        <Kpi
          label="ارزش کل (ریال)"
          value={formatMoney(kpis?.total_value_base ?? "0", "IRR")}
          sub="معادل ارز پایه"
        />
        <Kpi
          label="اقساط معوق"
          value={kpis?.overdue_installments ?? 0}
          sub={formatMoney(kpis?.overdue_amount ?? "0", "IRR")}
          tone={(kpis?.overdue_installments ?? 0) > 0 ? "danger" : undefined}
        />
        <Kpi
          label="هشدارهای باز"
          value={kpis?.unacknowledged_alerts ?? 0}
          sub={`${kpis?.critical_alerts ?? 0} بحرانی`}
          tone={(kpis?.critical_alerts ?? 0) > 0 ? "danger" : undefined}
        />
        <Kpi
          label="میانگین زمان محاسبه"
          value={kpis?.avg_calc_duration_ms ? `${kpis.avg_calc_duration_ms.toFixed(2)} ms` : "—"}
          sub="آستانه: ۵۰ میلی‌ثانیه"
          tone={kpis?.avg_calc_duration_ms && kpis.avg_calc_duration_ms > 50 ? "danger" : "success"}
        />
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h2>وضعیت گزارش‌ها</h2>
          <StatusPie data={statusData} />
        </div>
        <div className="card">
          <h2>روند ۱۲ ماه اخیر</h2>
          <TrendChart data={trendData} />
        </div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h2>توزیع ارزی (معادل ارز پایه)</h2>
          <CurrencyBars data={currencyData} />
        </div>

        <div className="card">
          <div className="row">
            <h2 style={{ margin: 0 }}>هشدارهای فعال</h2>
            <div className="spacer" />
            <span className="live-dot" data-off={!live}>{live ? "زنده" : "قطع"}</span>
          </div>
          {alerts.length === 0 ? (
            <p className="muted" style={{ marginTop: 16 }}>هشدار بازی وجود ندارد ✓</p>
          ) : (
            <div className="stack" style={{ marginTop: 12 }}>
              {alerts.map((alert) => (
                <div key={alert.id} className="row" style={{ alignItems: "flex-start" }}>
                  <span className={`badge badge-${alert.severity}`}>
                    {SEVERITY_LABELS[alert.severity]}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "0.88rem" }}>{alert.title}</div>
                    <div className="muted" style={{ fontSize: "0.76rem" }}>
                      {formatDate(alert.created_at)}
                    </div>
                  </div>
                  <button
                    className="btn ghost"
                    style={{ fontSize: "0.75rem", padding: "4px 10px" }}
                    onClick={async () => {
                      await api.acknowledgeAlert(alert.id);
                      void load();
                    }}
                  >
                    تأیید
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h2>آخرین گزارش‌ها</h2>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>شناسه</th>
                <th>عنوان</th>
                <th>مبلغ</th>
                <th>ارز</th>
                <th>وضعیت</th>
                <th>تاریخ ایجاد</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((report) => (
                <tr key={report.id}>
                  <td className="mono">{report.reference}</td>
                  <td>{report.title}</td>
                  <td style={{ fontVariantNumeric: "tabular-nums" }}>
                    {formatMoney(report.principal, report.currency)}
                  </td>
                  <td>{report.currency}</td>
                  <td>
                    <span className={`badge ${statusBadge(report.status)}`}>
                      {STATUS_LABELS[report.status] ?? report.status}
                    </span>
                  </td>
                  <td className="muted">{formatDate(report.created_at)}</td>
                </tr>
              ))}
              {recent.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted" style={{ textAlign: "center", padding: 24 }}>
                    هنوز گزارشی ثبت نشده است
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Kpi({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: "success" | "danger";
}) {
  const color =
    tone === "danger" ? "var(--danger)" : tone === "success" ? "var(--success)" : undefined;
  return (
    <div className="card">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ color }}>{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}

export function statusBadge(status: string): string {
  if (status === "approved") return "badge-approved";
  if (status === "rejected" || status === "cancelled") return "badge-rejected";
  if (status === "draft") return "badge-draft";
  return "badge-pending";
}
