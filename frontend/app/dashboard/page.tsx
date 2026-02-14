"use client";

import { useQuery } from "@tanstack/react-query";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import {
  DollarSign,
  Clock,
  ShieldAlert,
  CheckCircle,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

type Stats = {
  spend_today: number;
  spend_month: number;
  pending_approvals: number;
  blocked_count: number;
  completed_count: number;
  payments_today: number;
  daily_spend: { date: string; amount: number }[];
};

type Payment = {
  id: string;
  amount: number;
  currency: string;
  status: string;
  created_at: string;
  vendor_id: string;
  category: string | null;
};

export default function DashboardPage() {
  const { data: stats } = useQuery<Stats>({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.get("/dashboard/stats"),
  });

  const { data: recentPayments } = useQuery<Payment[]>({
    queryKey: ["recent-payments"],
    queryFn: () => api.get("/payments?limit=5"),
  });

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-neutral-900">Dashboard</h1>
        <p className="text-xs text-neutral-400 mt-1">
          Payment orchestration overview
        </p>
      </div>

      {/* Stat cards */}
      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Month Spend"
          value={formatCurrency(stats?.spend_month ?? 0)}
          subtitle={`Today: ${formatCurrency(stats?.spend_today ?? 0)}`}
          icon={<DollarSign className="h-4 w-4 text-neutral-400" />}
        />
        <StatCard
          title="Pending Approvals"
          value={String(stats?.pending_approvals ?? 0)}
          subtitle="Awaiting review"
          icon={<Clock className="h-4 w-4 text-neutral-400" />}
        />
        <StatCard
          title="Blocked"
          value={String(stats?.blocked_count ?? 0)}
          subtitle="This month"
          icon={<ShieldAlert className="h-4 w-4 text-neutral-400" />}
        />
        <StatCard
          title="Completed"
          value={String(stats?.completed_count ?? 0)}
          subtitle="This month"
          icon={<CheckCircle className="h-4 w-4 text-neutral-400" />}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Chart */}
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Daily Volume (7d)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats?.daily_spend ?? []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#a3a3a3" />
                  <YAxis tick={{ fontSize: 11 }} stroke="#a3a3a3" />
                  <Tooltip
                    formatter={(value: number | undefined) => formatCurrency(value ?? 0)}
                    contentStyle={{
                      borderRadius: "8px",
                      border: "1px solid #e5e5e5",
                      boxShadow: "none",
                      fontSize: "12px",
                    }}
                  />
                  <Bar
                    dataKey="amount"
                    fill="#171717"
                    radius={[3, 3, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Recent payments */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Payments</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {recentPayments?.length === 0 && (
              <p className="text-xs text-neutral-400">No payments yet</p>
            )}
            {recentPayments?.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-lg border border-neutral-100 px-3 py-2.5"
              >
                <div>
                  <p className="text-sm font-medium text-neutral-900">
                    {formatCurrency(p.amount, p.currency)}
                  </p>
                  <p className="text-[11px] text-neutral-400">
                    {p.category ?? "—"}
                  </p>
                </div>
                <Badge status={p.status}>{p.status}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

function StatCard({
  title,
  value,
  subtitle,
  icon,
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-neutral-400">{title}</p>
            <p className="mt-1 text-xl font-semibold text-neutral-900">{value}</p>
            <p className="text-[11px] text-neutral-400 mt-0.5">{subtitle}</p>
          </div>
          <div>{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}
