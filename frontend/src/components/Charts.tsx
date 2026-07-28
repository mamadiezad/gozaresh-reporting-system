"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { STATUS_LABELS } from "@/lib/api";

const PALETTE = ["#4f8cff", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#22d3ee", "#fb923c"];

const axisStyle = { fill: "#96a3bf", fontSize: 12 };
const tooltipStyle = {
  background: "#1e2740",
  border: "1px solid #2a3550",
  borderRadius: 10,
  color: "#e8edf7",
  fontSize: 13,
};

export function StatusPie({ data }: { data: Array<{ status: string; count: number }> }) {
  const rows = data.map((d) => ({ name: STATUS_LABELS[d.status] ?? d.status, value: d.count }));
  if (!rows.length) return <Empty />;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie data={rows} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={3}>
          {rows.map((_, index) => (
            <Cell key={index} fill={PALETTE[index % PALETTE.length]} />
          ))}
        </Pie>
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12, color: "#96a3bf" }} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function TrendChart({
  data,
}: {
  data: Array<{ month: string; count: number; approved: number }>;
}) {
  if (!data.length) return <Empty />;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a3550" />
        <XAxis dataKey="month" tick={axisStyle} reversed />
        <YAxis tick={axisStyle} orientation="right" allowDecimals={false} />
        <Tooltip contentStyle={tooltipStyle} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line type="monotone" dataKey="count" name="کل گزارش‌ها" stroke="#4f8cff" strokeWidth={2} dot={{ r: 3 }} />
        <Line type="monotone" dataKey="approved" name="تأییدشده" stroke="#34d399" strokeWidth={2} dot={{ r: 3 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function CurrencyBars({
  data,
}: {
  data: Array<{ currency: string; count: number; total_in_base: string }>;
}) {
  const rows = data.map((d) => ({ currency: d.currency, مبلغ: Number(d.total_in_base) || 0 }));
  if (!rows.length) return <Empty />;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={rows} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#2a3550" />
        <XAxis dataKey="currency" tick={axisStyle} reversed />
        <YAxis tick={axisStyle} orientation="right" tickFormatter={(v) => new Intl.NumberFormat("fa-IR", { notation: "compact" }).format(v)} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => new Intl.NumberFormat("fa-IR").format(v)} />
        <Bar dataKey="مبلغ" radius={[6, 6, 0, 0]}>
          {rows.map((_, index) => (
            <Cell key={index} fill={PALETTE[index % PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function Empty() {
  return (
    <div style={{ display: "grid", placeItems: "center", height: 260 }} className="muted">
      داده‌ای برای نمایش وجود ندارد
    </div>
  );
}
