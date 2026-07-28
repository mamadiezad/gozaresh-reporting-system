/**
 * Typed API client for the Gozaresh backend.
 * Handles JWT storage, automatic refresh on 401 and the WebSocket channel.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE ?? "ws://localhost:8000/api/v1";

/**
 * A page served over HTTPS cannot call an http:// API — the browser blocks it
 * as mixed content and `fetch` rejects with an opaque "Failed to fetch".
 * Detect that specific misconfiguration so the user gets a real explanation.
 */
function mixedContentProblem(): boolean {
  if (typeof window === "undefined") return false;
  return window.location.protocol === "https:" && API_BASE.startsWith("http://");
}

function unreachableMessage(): string {
  if (mixedContentProblem()) {
    return (
      `این صفحه روی HTTPS اجرا می‌شود اما آدرس API روی HTTP است (${API_BASE}). ` +
      "مرورگر چنین درخواستی را مسدود می‌کند. مقدار NEXT_PUBLIC_API_BASE را روی یک آدرس https:// تنظیم کنید."
    );
  }
  return (
    `اتصال به سرور برقرار نشد (${API_BASE}). ` +
    "مطمئن شوید بک‌اند در حال اجراست: docker compose up — یا uvicorn app.main:app --reload"
  );
}

const ACCESS_KEY = "gozaresh.access";
const REFRESH_KEY = "gozaresh.refresh";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export type Role =
  | "viewer"
  | "requester"
  | "finance_manager"
  | "inspector"
  | "ceo"
  | "auditor"
  | "admin";

export type ReportStatus =
  | "draft"
  | "submitted"
  | "pending_finance"
  | "pending_inspector"
  | "pending_ceo"
  | "approved"
  | "rejected"
  | "cancelled";

export interface User {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
}

export interface Report {
  id: number;
  reference: string;
  title: string;
  status: ReportStatus;
  principal: string;
  currency: string;
  total_payable: string | null;
  amount_in_base: string | null;
  monthly_installment: string | null;
  calc_duration_ms: number | null;
  department: string;
  counterparty: string;
  created_at: string;
  submitted_at: string | null;
}

export interface WorkflowStage {
  stage: string;
  order: number;
  status: "pending" | "approved" | "rejected" | "skipped";
  approver_id: number | null;
  comment: string;
  acted_at: string | null;
  signed: boolean;
  key_fingerprint: string | null;
}

export interface Kpis {
  total_reports: number;
  approved: number;
  rejected: number;
  pending: number;
  approval_rate_percent: string;
  total_value_base: string;
  overdue_installments: number;
  overdue_amount: string;
  unacknowledged_alerts: number;
  critical_alerts: number;
  avg_calc_duration_ms: number | null;
}

export interface Alert {
  id: number;
  report_id: number | null;
  kind: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  acknowledged: boolean;
  created_at: string;
}

export interface CalculationResult {
  principal: string;
  currency: string;
  total_interest: string;
  total_payable: string;
  periodic_payment: string;
  effective_annual_rate: string;
  display_total: string;
  amount_in_base: string | null;
  fx_rate: string | null;
  fx_source: string | null;
  duration_ms: number;
  within_sla: boolean;
  sla_ms: number;
  schedule: Array<{
    number: number;
    due_date: string;
    amount: string;
    principal_component: string;
    interest_component: string;
    remaining_balance: string;
  }>;
}

// ---------------------------------------------------------------------------
// Token storage
// ---------------------------------------------------------------------------
export const tokens = {
  get access() {
    return typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY);
  },
  get refresh() {
    return typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    localStorage.setItem(ACCESS_KEY, access);
    localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
  },
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------------------------------------------------------------------------
// Core fetch wrapper
// ---------------------------------------------------------------------------
async function request<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }
  const access = tokens.access;
  if (access) headers.set("Authorization", `Bearer ${access}`);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    // fetch() only rejects on network/CORS/mixed-content failures, never on
    // HTTP error statuses — so this is always a connectivity problem.
    throw new ApiError(unreachableMessage(), 0);
  }

  if (response.status === 401 && retry && tokens.refresh) {
    const refreshed = await refreshSession();
    if (refreshed) return request<T>(path, init, false);
  }

  if (!response.ok) {
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = await response.text();
    }
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(detail, response.status, body);
  }

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  return (contentType.includes("application/json")
    ? await response.json()
    : await response.text()) as T;
}

async function refreshSession(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: tokens.refresh }),
    });
    if (!response.ok) {
      tokens.clear();
      return false;
    }
    const data = await response.json();
    tokens.set(data.access_token, data.refresh_token);
    return true;
  } catch {
    tokens.clear();
    return false;
  }
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------
export const api = {
  // auth
  async login(username: string, password: string) {
    const data = await request<{
      access_token: string;
      refresh_token: string;
      user: User;
    }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    tokens.set(data.access_token, data.refresh_token);
    return data.user;
  },
  logout: () => {
    tokens.clear();
  },
  me: () => request<User>("/auth/me"),

  // reports
  reports: (params: Record<string, string | number> = {}) =>
    request<{ items: Report[]; total: number; pages: number }>(
      `/reports?${new URLSearchParams(params as Record<string, string>)}`,
    ),
  report: (id: number) => request<Report & { steps: WorkflowStage[] }>(`/reports/${id}`),
  createReport: (payload: Record<string, unknown>) =>
    request<Report>("/reports", { method: "POST", body: JSON.stringify(payload) }),
  submitReport: (id: number) => request<Report>(`/reports/${id}/submit`, { method: "POST" }),
  decide: (id: number, approved: boolean, comment: string) =>
    request(`/reports/${id}/decision`, {
      method: "POST",
      body: JSON.stringify({ approved, comment }),
    }),
  inbox: () => request<Report[]>("/reports/inbox"),
  workflow: (id: number) =>
    request<{ current_stage: string | null; you_can_act: boolean; stages: WorkflowStage[] }>(
      `/reports/${id}/workflow`,
    ),
  signatures: (id: number) =>
    request<{ all_valid: boolean | null; content_unchanged: boolean | null; steps: unknown[] }>(
      `/reports/${id}/signatures`,
    ),
  installments: (id: number) => request<unknown[]>(`/reports/${id}/installments`),

  // calculations
  preview: (payload: Record<string, unknown>) =>
    request<CalculationResult>("/calculations/preview", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  rate: (base: string, quote: string) =>
    request<{ rate: string; source: string; fetched_at: string }>(
      `/calculations/rates/${base}/${quote}`,
    ),
  rateTable: (base: string) =>
    request<{ base: string; rates: Record<string, string> }>(`/calculations/rates/${base}`),
  benchmark: (iterations = 100) =>
    request<Record<string, number>>(`/calculations/benchmark?iterations=${iterations}`),

  // dashboard
  overview: () => request<Record<string, unknown>>("/dashboard/overview"),
  kpis: () => request<Kpis>("/dashboard/kpis"),
  chartStatus: () => request<Array<{ status: string; count: number }>>("/dashboard/charts/status"),
  chartCurrency: () =>
    request<Array<{ currency: string; count: number; total_in_base: string }>>(
      "/dashboard/charts/currency",
    ),
  chartTrend: (months = 12) =>
    request<Array<{ month: string; count: number; approved: number; value_base: string }>>(
      `/dashboard/charts/trend?months=${months}`,
    ),
  upcoming: (days = 30) => request<unknown[]>(`/dashboard/upcoming?days=${days}`),

  // alerts
  alerts: (params: Record<string, string> = {}) =>
    request<Alert[]>(`/alerts?${new URLSearchParams(params)}`),
  acknowledgeAlert: (id: number) => request<Alert>(`/alerts/${id}/acknowledge`, { method: "POST" }),
  scanAlerts: () => request<Record<string, number>>("/alerts/scan", { method: "POST" }),

  // audit
  auditLogs: (params: Record<string, string | number> = {}) =>
    request<unknown[]>(`/audit/logs?${new URLSearchParams(params as Record<string, string>)}`),
  verifyChain: () =>
    request<{ valid: boolean; checked: number; broken_at_sequence: number | null }>("/audit/verify"),

  // integrations
  submitToMoadian: (id: number) =>
    request<Record<string, unknown>>(`/integrations/moadian/${id}/submit`, { method: "POST" }),
  requestSettlement: (id: number, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/integrations/bank/${id}/settle`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  pushToAccounting: (id: number) =>
    request<Record<string, unknown>>(`/integrations/accounting/${id}/push`, { method: "POST" }),
};

// ---------------------------------------------------------------------------
// WebSocket with exponential-backoff reconnect
// ---------------------------------------------------------------------------
export interface LiveEvent {
  event: string;
  topic: string;
  timestamp?: string;
  data: Record<string, unknown>;
}

export function connectLive(onEvent: (event: LiveEvent) => void): () => void {
  let socket: WebSocket | null = null;
  let attempt = 0;
  let heartbeat: ReturnType<typeof setInterval> | null = null;
  let closed = false;

  const open = () => {
    const token = tokens.access;
    if (!token || closed) return;

    socket = new WebSocket(`${WS_BASE}/ws/dashboard?token=${encodeURIComponent(token)}`);

    socket.onopen = () => {
      attempt = 0;
      heartbeat = setInterval(() => socket?.readyState === WebSocket.OPEN && socket.send("ping"), 25_000);
    };
    socket.onmessage = (message) => {
      try {
        onEvent(JSON.parse(message.data) as LiveEvent);
      } catch {
        /* ignore malformed frames */
      }
    };
    socket.onclose = () => {
      if (heartbeat) clearInterval(heartbeat);
      if (closed) return;
      attempt += 1;
      setTimeout(open, Math.min(30_000, 1000 * 2 ** attempt));
    };
    socket.onerror = () => socket?.close();
  };

  open();

  return () => {
    closed = true;
    if (heartbeat) clearInterval(heartbeat);
    socket?.close();
  };
}

// ---------------------------------------------------------------------------
// Formatting helpers (fa-IR)
// ---------------------------------------------------------------------------
const ZERO_DECIMAL = new Set(["IRR", "IRT", "JPY", "KRW"]);

export function formatMoney(value: string | number | null, currency = "IRR"): string {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(numeric)) return String(value);
  const digits = ZERO_DECIMAL.has(currency.toUpperCase()) ? 0 : 2;
  return new Intl.NumberFormat("fa-IR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(numeric);
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "medium",
    timeStyle: "short",
    calendar: "persian",
  }).format(new Date(value));
}

export const STATUS_LABELS: Record<string, string> = {
  draft: "پیش‌نویس",
  submitted: "ارسال‌شده",
  pending_finance: "در انتظار مدیر مالی",
  pending_inspector: "در انتظار بازرس",
  pending_ceo: "در انتظار مدیرعامل",
  approved: "تأییدشده",
  rejected: "ردشده",
  cancelled: "لغوشده",
};

export const STAGE_LABELS: Record<string, string> = {
  finance_manager: "مدیر مالی",
  inspector: "بازرس",
  ceo: "مدیرعامل",
};

export const SEVERITY_LABELS: Record<string, string> = {
  info: "اطلاع",
  warning: "هشدار",
  critical: "بحرانی",
};
