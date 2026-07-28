"use client";

import { useCallback, useEffect, useState } from "react";

import AuditTrail from "@/components/AuditTrail";
import Calculator from "@/components/Calculator";
import Dashboard from "@/components/Dashboard";
import Footer from "@/components/Footer";
import Login from "@/components/Login";
import Reports from "@/components/Reports";
import { api, connectLive, tokens, type LiveEvent, type User } from "@/lib/api";

type Tab = "dashboard" | "calculator" | "reports" | "audit";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "dashboard", label: "داشبورد" },
  { id: "calculator", label: "محاسبه‌گر" },
  { id: "reports", label: "گزارش‌ها و گردش‌کار" },
  { id: "audit", label: "مسیر حسابرسی" },
];

interface Toast {
  id: number;
  text: string;
  severity: string;
}

export default function DashboardClient() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [tab, setTab] = useState<Tab>("dashboard");
  const [live, setLive] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [refreshToken, setRefreshToken] = useState(0);

  // restore an existing session on first paint
  useEffect(() => {
    if (!tokens.access) {
      setChecking(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => tokens.clear())
      .finally(() => setChecking(false));
  }, []);

  const pushToast = useCallback((text: string, severity = "info") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current.slice(-4), { id, text, severity }]);
    setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), 7000);
  }, []);

  // live channel
  useEffect(() => {
    if (!user) return;
    setLive(true);

    const disconnect = connectLive((event: LiveEvent) => {
      const data = event.data as Record<string, string>;
      switch (event.event) {
        case "alert.raised":
          pushToast(`🔔 ${data.title}`, String(data.severity ?? "warning"));
          setRefreshToken((n) => n + 1);
          break;
        case "workflow.updated":
          pushToast(
            `${data.reference}: ${data.decision === "approved" ? "تأیید" : "رد"} در مرحله ${data.stage}`,
          );
          setRefreshToken((n) => n + 1);
          break;
        case "workflow.pending":
          pushToast(`⏳ ${data.reference} در انتظار ${data.assignee_role}`);
          setRefreshToken((n) => n + 1);
          break;
        case "workflow.completed":
          pushToast(`✅ ${data.reference}: ${data.status}`);
          setRefreshToken((n) => n + 1);
          break;
        case "report.created":
          pushToast(`📄 گزارش جدید: ${data.reference}`);
          setRefreshToken((n) => n + 1);
          break;
        case "installment.paid":
          pushToast(`💰 قسط ${data.number} از ${data.reference} پرداخت شد`);
          setRefreshToken((n) => n + 1);
          break;
        default:
          break;
      }
    });

    return () => {
      disconnect();
      setLive(false);
    };
  }, [user, pushToast]);

  if (checking) return <div className="center muted">در حال بررسی نشست…</div>;
  if (!user) {
    return (
      <>
        <Login onSuccess={setUser} />
        <Footer />
      </>
    );
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          گزارش
          <small>سامانه گزارش‌گیری سازمانی</small>
        </div>

        <nav className="nav">
          {TABS.map((item) => (
            <button key={item.id} data-active={tab === item.id} onClick={() => setTab(item.id)}>
              {item.label}
            </button>
          ))}
        </nav>

        <div style={{ marginTop: 32, fontSize: "0.8rem" }} className="muted">
          <div>{user.full_name || user.username}</div>
          <div style={{ fontSize: "0.75rem" }}>نقش: {user.role}</div>
          <button
            className="btn ghost"
            style={{ marginTop: 10, width: "100%", fontSize: "0.8rem" }}
            onClick={() => {
              api.logout();
              setUser(null);
            }}
          >
            خروج
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <h1>{TABS.find((t) => t.id === tab)?.label}</h1>
          <span className="live-dot" data-off={!live}>
            {live ? "اتصال زنده برقرار است" : "بدون اتصال زنده"}
          </span>
        </header>

        {tab === "dashboard" && <Dashboard live={live} refreshToken={refreshToken} />}
        {tab === "calculator" && <Calculator />}
        {tab === "reports" && <Reports user={user} refreshToken={refreshToken} />}
        {tab === "audit" && <AuditTrail refreshToken={refreshToken} />}

        <Footer />
      </main>

      <div className="toast-stack">
        {toasts.map((toast) => (
          <div key={toast.id} className="toast" data-severity={toast.severity}>
            {toast.text}
          </div>
        ))}
      </div>
    </div>
  );
}
