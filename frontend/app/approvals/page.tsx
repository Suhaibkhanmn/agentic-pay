"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

type Approval = {
  id: string;
  payment_request_id: string;
  status: string;
  assigned_to: string | null;
  decided_by: string | null;
  reason: string | null;
  created_at: string;
};

type Payment = {
  id: string;
  amount: number;
  currency: string;
  description: string | null;
  category: string | null;
  vendor_id: string;
};

type AuditEntry = {
  detail: {
    agent_assessment?: {
      risk_score: number;
      risk_explanation: string;
      should_escalate: boolean;
      suspicious_patterns: string[];
    };
    escalated_by_agent?: boolean;
    risk_signals?: { signal: string; severity: string; detail: string }[];
  };
};

export default function ApprovalsPage() {
  const qc = useQueryClient();

  const { data: approvals, isLoading } = useQuery<Approval[]>({
    queryKey: ["approvals-pending"],
    queryFn: () => api.get("/approvals/pending"),
  });

  const decideMut = useMutation({
    mutationFn: ({
      id,
      action,
      reason,
    }: {
      id: string;
      action: string;
      reason?: string;
    }) => api.post(`/approvals/${id}/decide`, { action, reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals-pending"] });
      qc.invalidateQueries({ queryKey: ["dashboard-stats"] });
    },
  });

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-neutral-900">
          Pending Approvals
        </h1>
        <p className="text-xs text-neutral-400 mt-1">
          Review and decide on payment requests requiring approval
        </p>
      </div>

      {isLoading && <p className="text-xs text-neutral-400">Loading...</p>}

      {approvals?.length === 0 && !isLoading && (
        <Card>
          <CardContent className="py-12 text-center">
            <CheckCircle className="mx-auto mb-3 h-8 w-8 text-neutral-300" />
            <p className="text-sm font-medium text-neutral-700">All clear</p>
            <p className="text-xs text-neutral-400 mt-1">
              No pending approvals at the moment
            </p>
          </CardContent>
        </Card>
      )}

      <div className="space-y-3">
        {approvals?.map((a) => (
          <ApprovalCard
            key={a.id}
            approval={a}
            onDecide={(action) =>
              decideMut.mutate({ id: a.id, action })
            }
            deciding={decideMut.isPending}
          />
        ))}
      </div>
    </AppShell>
  );
}

function ApprovalCard({
  approval,
  onDecide,
  deciding,
}: {
  approval: Approval;
  onDecide: (action: "approve" | "reject") => void;
  deciding: boolean;
}) {
  const { data: payment } = useQuery<Payment>({
    queryKey: ["payment", approval.payment_request_id],
    queryFn: () => api.get(`/payments/${approval.payment_request_id}`),
  });

  const { data: auditLogs } = useQuery<AuditEntry[]>({
    queryKey: ["audit", approval.payment_request_id],
    queryFn: () =>
      api.get(`/audit?payment_request_id=${approval.payment_request_id}`),
  });

  const evalLog = auditLogs?.find(
    (a) => a.detail?.agent_assessment
  );
  const agent = evalLog?.detail?.agent_assessment;
  const riskSignals = evalLog?.detail?.risk_signals;

  return (
    <Card>
      <CardContent className="py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          {/* Payment info */}
          <div className="flex-1 space-y-2">
            <div className="flex items-center gap-3">
              <span className="text-lg font-semibold text-neutral-900">
                {formatCurrency(payment?.amount ?? 0, payment?.currency)}
              </span>
              <Badge status="REQUIRE_APPROVAL">Needs Approval</Badge>
              {evalLog?.detail?.escalated_by_agent && (
                <Badge status="BLOCKED">
                  <AlertTriangle className="mr-1 h-3 w-3" />
                  Agent Escalated
                </Badge>
              )}
            </div>
            <p className="text-sm text-neutral-500">
              {payment?.description ?? "No description"}
            </p>
            <p className="text-xs text-neutral-400">
              Category: {payment?.category ?? "—"}
            </p>

            {/* Agent reasoning */}
            {agent && (
              <div className="mt-3 rounded-lg bg-neutral-50 border border-neutral-200 p-3">
                <p className="text-[11px] font-medium text-neutral-700 mb-1">
                  Agent Assessment · Risk: {agent.risk_score}/100
                </p>
                <p className="text-xs text-neutral-500 leading-relaxed">
                  {agent.risk_explanation}
                </p>
                {agent.suspicious_patterns.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {agent.suspicious_patterns.map((p, i) => (
                      <span
                        key={i}
                        className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-600"
                      >
                        {p}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Risk signals */}
            {riskSignals && riskSignals.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {riskSignals.map((s, i) => (
                  <span
                    key={i}
                    className={`rounded-full px-2 py-0.5 text-[11px] ${s.severity === "high"
                      ? "bg-red-50 text-red-500"
                      : s.severity === "medium"
                        ? "bg-amber-50 text-amber-500"
                        : "bg-neutral-100 text-neutral-500"
                      }`}
                  >
                    {s.signal}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-2 lg:flex-col">
            <Button
              onClick={() => onDecide("approve")}
              disabled={deciding}
              className="gap-1"
            >
              <CheckCircle className="h-3.5 w-3.5" /> Approve
            </Button>
            <Button
              variant="destructive"
              onClick={() => onDecide("reject")}
              disabled={deciding}
              className="gap-1"
            >
              <XCircle className="h-3.5 w-3.5" /> Reject
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
