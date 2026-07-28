"use client";

import { useCallback, useEffect, useState } from "react";

import { api, formatDate } from "@/lib/api";

interface LogEntry {
  id: number;
  sequence: number;
  actor_username: string;
  actor_role: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  summary: string;
  ip_address: string | null;
  previous_hash: string;
  entry_hash: string;
  created_at: string;
}

const ACTION_LABELS: Record<string, string> = {
  create: "ایجاد",
  update: "ویرایش",
  delete: "حذف",
  login: "ورود",
  login_failed: "ورود ناموفق",
  logout: "خروج",
  submit: "ارسال",
  approve: "تأیید",
  reject: "رد",
  calculate: "محاسبه",
  export: "خروجی‌گیری",
  integration: "یکپارچه‌سازی",
  alert: "هشدار",
  security: "امنیت",
};

export default function AuditTrail({ refreshToken }: { refreshToken: number }) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [chain, setChain] = useState<{ valid: boolean; checked: number; broken_at_sequence: number | null } | null>(
    null,
  );
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const params: Record<string, string | number> = { limit: 100 };
      if (filter) params.action = filter;
      const [entries, verification] = await Promise.all([api.auditLogs(params), api.verifyChain()]);
      setLogs(entries as LogEntry[]);
      setChain(verification);
    } catch (err) {
      setError(err instanceof Error ? err.message : "دسترسی به گزارش حسابرسی امکان‌پذیر نیست");
    }
  }, [filter]);

  useEffect(() => {
    void load();
  }, [load, refreshToken]);

  const verifyNow = async () => {
    setBusy(true);
    try {
      setChain(await api.verifyChain());
    } finally {
      setBusy(false);
    }
  };

  if (error) {
    return (
      <div className="card">
        <p className="muted" style={{ margin: 0 }}>{error}</p>
        <p className="muted" style={{ fontSize: "0.82rem" }}>
          دسترسی به مسیر حسابرسی تنها برای نقش‌های بازرس، حسابرس، مدیرعامل و مدیر سیستم مجاز است.
        </p>
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card">
        <div className="row">
          <h2 style={{ margin: 0 }}>یکپارچگی زنجیره حسابرسی</h2>
          <div className="spacer" />
          <button className="btn ghost" disabled={busy} onClick={verifyNow}>
            {busy ? "در حال بررسی…" : "بررسی مجدد"}
          </button>
        </div>

        {chain && (
          <div className="row" style={{ marginTop: 14 }}>
            <span className={`badge ${chain.valid ? "badge-approved" : "badge-rejected"}`}>
              {chain.valid ? "زنجیره سالم ✓" : "دستکاری شناسایی شد ✗"}
            </span>
            <span className="muted" style={{ fontSize: "0.85rem" }}>
              {chain.checked.toLocaleString("fa-IR")} رکورد بررسی شد
            </span>
            {!chain.valid && chain.broken_at_sequence && (
              <span style={{ color: "var(--danger)", fontSize: "0.85rem" }}>
                نقطه شکست: رکورد شماره {chain.broken_at_sequence}
              </span>
            )}
          </div>
        )}

        <p className="muted" style={{ fontSize: "0.8rem", marginBottom: 0 }}>
          هر رکورد شامل هش رکورد قبلی است؛ هرگونه تغییر یا حذف در تاریخچه، زنجیره را می‌شکند و در همین
          بخش گزارش می‌شود.
        </p>
      </div>

      <div className="card">
        <div className="row" style={{ marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>رویدادها</h2>
          <div className="spacer" />
          <select value={filter} onChange={(e) => setFilter(e.target.value)} style={{ width: 180 }}>
            <option value="">همه رویدادها</option>
            {Object.entries(ACTION_LABELS).map(([key, label]) => (
              <option key={key} value={key}>{label}</option>
            ))}
          </select>
        </div>

        <div style={{ overflowX: "auto", maxHeight: 520, overflowY: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>زمان</th>
                <th>کاربر</th>
                <th>عملیات</th>
                <th>شرح</th>
                <th>هش</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td className="mono">{log.sequence}</td>
                  <td className="muted" style={{ whiteSpace: "nowrap" }}>{formatDate(log.created_at)}</td>
                  <td>
                    {log.actor_username}
                    <span className="muted" style={{ fontSize: "0.72rem" }}> ({log.actor_role})</span>
                  </td>
                  <td>
                    <span className="badge badge-info">{ACTION_LABELS[log.action] ?? log.action}</span>
                  </td>
                  <td style={{ maxWidth: 320 }}>{log.summary}</td>
                  <td className="mono muted" title={log.entry_hash}>{log.entry_hash.slice(0, 12)}…</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted" style={{ textAlign: "center", padding: 24 }}>
                    رویدادی ثبت نشده است
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
