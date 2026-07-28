"use client";

import { useCallback, useEffect, useState } from "react";

import { statusBadge } from "@/components/Dashboard";
import {
  api,
  formatDate,
  formatMoney,
  STAGE_LABELS,
  STATUS_LABELS,
  type Report,
  type User,
  type WorkflowStage,
} from "@/lib/api";

export default function Reports({ user, refreshToken }: { user: User; refreshToken: number }) {
  const [reports, setReports] = useState<Report[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [stages, setStages] = useState<WorkflowStage[]>([]);
  const [canAct, setCanAct] = useState(false);
  const [signatures, setSignatures] = useState<{ all_valid: boolean | null } | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const loadList = useCallback(async () => {
    const data = await api.reports({ page_size: 50 });
    setReports(data.items);
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    const [wf, sig] = await Promise.all([api.workflow(id), api.signatures(id)]);
    setStages(wf.stages);
    setCanAct(wf.you_can_act);
    setSignatures(sig);
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList, refreshToken]);

  useEffect(() => {
    if (selected) void loadDetail(selected);
  }, [selected, loadDetail, refreshToken]);

  const act = async (approved: boolean) => {
    if (!selected) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.decide(selected, approved, comment);
      setComment("");
      setMessage(approved ? "تأیید ثبت و امضا شد ✓" : "گزارش رد شد");
      await Promise.all([loadList(), loadDetail(selected)]);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "خطا در ثبت تصمیم");
    } finally {
      setBusy(false);
    }
  };

  const submit = async (id: number) => {
    setBusy(true);
    setMessage(null);
    try {
      await api.submitReport(id);
      setMessage("گزارش برای تأیید ارسال شد ✓");
      await loadList();
      if (selected === id) await loadDetail(id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "ارسال ناموفق بود");
    } finally {
      setBusy(false);
    }
  };

  const current = reports.find((r) => r.id === selected);

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card">
        <h2>گزارش‌ها</h2>
        <div style={{ overflowX: "auto" }}>
          <table>
            <thead>
              <tr>
                <th>شناسه</th>
                <th>عنوان</th>
                <th>مبلغ</th>
                <th>وضعیت</th>
                <th>ایجاد</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {reports.map((report) => (
                <tr
                  key={report.id}
                  style={{ cursor: "pointer", background: selected === report.id ? "var(--surface-2)" : undefined }}
                  onClick={() => setSelected(report.id)}
                >
                  <td className="mono">{report.reference}</td>
                  <td>{report.title}</td>
                  <td style={{ fontVariantNumeric: "tabular-nums" }}>
                    {formatMoney(report.principal, report.currency)} {report.currency}
                  </td>
                  <td>
                    <span className={`badge ${statusBadge(report.status)}`}>
                      {STATUS_LABELS[report.status] ?? report.status}
                    </span>
                  </td>
                  <td className="muted">{formatDate(report.created_at)}</td>
                  <td>
                    {report.status === "draft" && (
                      <button
                        className="btn"
                        style={{ fontSize: "0.75rem", padding: "4px 12px" }}
                        disabled={busy}
                        onClick={(e) => {
                          e.stopPropagation();
                          void submit(report.id);
                        }}
                      >
                        ارسال
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {reports.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted" style={{ textAlign: "center", padding: 24 }}>
                    گزارشی یافت نشد
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {current && (
        <div className="card">
          <div className="row">
            <h2 style={{ margin: 0 }}>
              گردش‌کار — <span className="mono">{current.reference}</span>
            </h2>
            <div className="spacer" />
            {signatures?.all_valid !== null && (
              <span className={`badge ${signatures?.all_valid ? "badge-approved" : "badge-rejected"}`}>
                {signatures?.all_valid ? "امضاها معتبر ✓" : "امضا نامعتبر ✗"}
              </span>
            )}
          </div>

          <div className="stages" style={{ marginTop: 16 }}>
            {stages.map((stage) => (
              <div key={stage.order} className="stage" data-status={stage.status}>
                <div style={{ fontWeight: 600 }}>{STAGE_LABELS[stage.stage] ?? stage.stage}</div>
                <div className="muted" style={{ fontSize: "0.78rem", marginTop: 4 }}>
                  {stage.status === "pending" && "در انتظار"}
                  {stage.status === "approved" && "تأیید شد"}
                  {stage.status === "rejected" && "رد شد"}
                  {stage.status === "skipped" && "انجام نشد"}
                </div>
                {stage.acted_at && (
                  <div className="muted" style={{ fontSize: "0.72rem" }}>{formatDate(stage.acted_at)}</div>
                )}
                {stage.comment && (
                  <div style={{ fontSize: "0.76rem", marginTop: 6 }}>«{stage.comment}»</div>
                )}
                {stage.signed && (
                  <div className="mono muted" style={{ fontSize: "0.66rem", marginTop: 6 }} title="اثر انگشت کلید امضا">
                    🔏 {stage.key_fingerprint?.slice(0, 16)}…
                  </div>
                )}
              </div>
            ))}
          </div>

          {canAct && (
            <div style={{ marginTop: 18 }}>
              <div className="field">
                <label htmlFor="comment">توضیح تصمیم (اختیاری)</label>
                <textarea
                  id="comment"
                  rows={2}
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  placeholder="دلیل تأیید یا رد…"
                />
              </div>
              <div className="row">
                <button className="btn success" disabled={busy} onClick={() => act(true)}>
                  تأیید و امضای دیجیتال
                </button>
                <button className="btn danger" disabled={busy} onClick={() => act(false)}>
                  رد درخواست
                </button>
              </div>
            </div>
          )}

          {message && (
            <p style={{ marginTop: 12, fontSize: "0.85rem", color: "var(--primary)" }}>{message}</p>
          )}
        </div>
      )}
    </div>
  );
}
