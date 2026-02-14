"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Eye } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/utils";

type Payment = {
  id: string;
  vendor_id: string;
  amount: number;
  currency: string;
  description: string | null;
  category: string | null;
  status: string;
  idempotency_key: string;
  created_at: string;
};

const STATUSES = [
  "",
  "PENDING",
  "APPROVED",
  "REQUIRE_APPROVAL",
  "BLOCKED",
  "REJECTED",
  "EXECUTING",
  "COMPLETED",
  "FAILED",
];

export default function PaymentsPage() {
  const [statusFilter, setStatusFilter] = useState("");

  const { data: payments, isLoading } = useQuery<Payment[]>({
    queryKey: ["payments", statusFilter],
    queryFn: () =>
      api.get(`/payments?limit=100${statusFilter ? `&status=${statusFilter}` : ""}`),
  });

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-neutral-900">Payments</h1>
        <p className="text-xs text-neutral-400 mt-1">
          All payment requests and their statuses
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4">
        <select
          className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="">All statuses</option>
          {STATUSES.filter(Boolean).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-100 text-left text-[11px] font-medium text-neutral-400 uppercase tracking-wider">
                  <th className="px-5 py-3">Amount</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Category</th>
                  <th className="px-5 py-3">Description</th>
                  <th className="px-5 py-3">Date</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-50">
                {isLoading && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-5 py-8 text-center text-xs text-neutral-400"
                    >
                      Loading...
                    </td>
                  </tr>
                )}
                {payments?.length === 0 && !isLoading && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-5 py-8 text-center text-xs text-neutral-400"
                    >
                      No payments found
                    </td>
                  </tr>
                )}
                {payments?.map((p) => (
                  <tr key={p.id} className="hover:bg-neutral-50/50 transition-colors">
                    <td className="px-5 py-3 font-medium text-neutral-900">
                      {formatCurrency(p.amount, p.currency)}
                    </td>
                    <td className="px-5 py-3">
                      <Badge status={p.status}>{p.status}</Badge>
                    </td>
                    <td className="px-5 py-3 text-neutral-500">
                      {p.category ?? "—"}
                    </td>
                    <td className="px-5 py-3 text-neutral-500 max-w-[200px] truncate">
                      {p.description ?? "—"}
                    </td>
                    <td className="px-5 py-3 text-neutral-400 text-xs">
                      {formatDate(p.created_at)}
                    </td>
                    <td className="px-5 py-3">
                      <Link href={`/payments/${p.id}`}>
                        <Button size="sm" variant="ghost">
                          <Eye className="h-3.5 w-3.5" />
                        </Button>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </AppShell>
  );
}
