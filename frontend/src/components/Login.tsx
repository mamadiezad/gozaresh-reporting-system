"use client";

import { useState } from "react";

import { api, type User } from "@/lib/api";

const DEMO_ACCOUNTS = [
  { username: "alice", label: "درخواست‌دهنده" },
  { username: "bob", label: "مدیر مالی" },
  { username: "carol", label: "بازرس" },
  { username: "dave", label: "مدیرعامل" },
  { username: "erin", label: "حسابرس" },
];

export default function Login({ onSuccess }: { onSuccess: (user: User) => void }) {
  const [username, setUsername] = useState("bob");
  const [password, setPassword] = useState("DemoPass!2024");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onSuccess(await api.login(username, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "ورود ناموفق بود");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="center">
      <form className="card" style={{ width: 380 }} onSubmit={submit}>
        <div className="brand" style={{ marginBottom: 20 }}>
          گزارش
          <small>سامانه گزارش‌گیری سازمانی</small>
        </div>

        <div className="field">
          <label htmlFor="username">نام کاربری</label>
          <input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </div>

        <div className="field">
          <label htmlFor="password">گذرواژه</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        {error && (
          <p style={{ color: "var(--danger)", fontSize: "0.85rem", marginTop: 0 }}>{error}</p>
        )}

        <button className="btn" style={{ width: "100%" }} disabled={busy} type="submit">
          {busy ? "در حال ورود…" : "ورود"}
        </button>

        <div style={{ marginTop: 18, fontSize: "0.8rem" }} className="muted">
          حساب‌های نمونه (گذرواژه یکسان: <span className="mono">DemoPass!2024</span>)
          <div className="row" style={{ marginTop: 8 }}>
            {DEMO_ACCOUNTS.map((account) => (
              <button
                key={account.username}
                type="button"
                className="btn ghost"
                style={{ fontSize: "0.75rem", padding: "5px 10px" }}
                onClick={() => setUsername(account.username)}
              >
                {account.label}
              </button>
            ))}
          </div>
        </div>
      </form>
    </div>
  );
}
