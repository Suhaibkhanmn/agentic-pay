"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/utils";

type AuditEntry = {
  id: string;
  payment_request_id: string | null;
  event_type: string;
  actor: string;
  detail: Record<string, unknown>;
  created_at: string;
};

const EVENT_TYPES = [
  "",
  "PAYMENT_EVALUATED",
  "APPROVAL_DECIDED",
  "PAYMENT_EXECUTED",
  "PAYMENT_DEAD_LETTER",
];

export default function AuditPage() {
  const [paymentId, setPaymentId] = useState("");
  const [eventType, setEventType] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);

  const queryParams = new URLSearchParams();
  if (paymentId) queryParams.set("payment_request_id", paymentId);
  if (eventType) queryParams.set("event_type", eventType);
  queryParams.set("limit", "100");
  const qs = queryParams.toString();

  const { data: logs, isLoading } = useQuery<AuditEntry[]>({
    queryKey: ["audit-logs", qs],
    queryFn: () => api.get(`/audit?${qs}`),
  });

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-neutral-900">Audit Log</h1>
        <p className="text-xs text-neutral-400 mt-1">
          Immutable record of every system event
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4 flex gap-3">
        <Input
          className="max-w-xs"
          placeholder="Filter by Payment ID"
          value={paymentId}
          onChange={(e) => setPaymentId(e.target.value)}
        />
        <select
          className="rounded-lg border border-neutral-200 bg-white px-3 py-2 text-xs text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900"
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
        >
          <option value="">All events</option>
          {EVENT_TYPES.filter(Boolean).map((t) => (
            <option key={t} value={t}>
              {t}
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
                  <th className="px-5 py-3">Event</th>
                  <th className="px-5 py-3">Actor</th>
                  <th className="px-5 py-3">Payment ID</th>
                  <th className="px-5 py-3">Date</th>
                  <th className="px-5 py-3">Detail</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-50">
                {isLoading && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-5 py-8 text-center text-xs text-neutral-400"
                    >
                      Loading...
                    </td>
                  </tr>
                )}
                {logs?.length === 0 && !isLoading && (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-5 py-8 text-center text-xs text-neutral-400"
                    >
                      No audit entries found
                    </td>
                  </tr>
                )}
                {logs?.map((log) => (
                  <tr key={log.id} className="hover:bg-neutral-50/50 transition-colors">
                    <td className="px-5 py-3">
                      <Badge
                        status={
                          log.event_type.includes("BLOCK") ||
                            log.event_type.includes("DEAD")
                            ? "BLOCKED"
                            : log.event_type.includes("EXECUTED")
                              ? "COMPLETED"
                              : "PENDING"
                        }
                      >
                        {log.event_type}
                      </Badge>
                    </td>
                    <td className="px-5 py-3 text-neutral-500">{log.actor}</td>
                    <td className="px-5 py-3 font-mono text-xs text-neutral-400">
                      {log.payment_request_id
                        ? log.payment_request_id.slice(0, 8) + "..."
                        : "—"}
                    </td>
                    <td className="px-5 py-3 text-xs text-neutral-400">
                      {formatDate(log.created_at)}
                    </td>
                    <td className="px-5 py-3">
                      <button
                        className="text-xs text-neutral-500 hover:text-neutral-900 transition-colors"
                        onClick={() =>
                          setExpanded(expanded === log.id ? null : log.id)
                        }
                      >
                        {expanded === log.id ? "Hide" : "Show"}
                      </button>
                      {expanded === log.id && (
                        <div className="mt-2 max-w-lg">
                          <div className="flex justify-end mb-1">
                            <button
                              className="text-[11px] text-neutral-400 hover:text-neutral-700 transition-colors"
                              onClick={() => {
                                navigator.clipboard.writeText(
                                  JSON.stringify(log.detail, null, 2)
                                );
                              }}
                            >
                              Copy
                            </button>
                          </div>
                          <pre className="overflow-auto rounded-lg bg-neutral-50 p-3 text-[11px] text-neutral-600 font-mono leading-relaxed">
                            {JSON.stringify(log.detail, null, 2)}
                          </pre>
                        </div>
                      )}
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
