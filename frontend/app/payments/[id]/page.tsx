"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Shield,
  Bot,
  CheckCircle,
  CreditCard,
  AlertTriangle,
} from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  invoice_ref: string | null;
  category: string | null;
  status: string;
  idempotency_key: string;
  created_by: string | null;
  created_at: string;
};

type AuditEntry = {
  id: string;
  event_type: string;
  actor: string;
  detail: Record<string, unknown>;
  created_at: string;
};

export default function PaymentDetailPage() {
  const params = useParams();
  const id = params.id as string;

  const { data: payment, isLoading } = useQuery<Payment>({
    queryKey: ["payment", id],
    queryFn: () => api.get(`/payments/${id}`),
  });

  const { data: auditLogs } = useQuery<AuditEntry[]>({
    queryKey: ["audit", id],
    queryFn: () => api.get(`/audit?payment_request_id=${id}`),
  });

  if (isLoading) {
    return (
      <AppShell>
        <p className="text-xs text-neutral-400">Loading...</p>
      </AppShell>
    );
  }

  if (!payment) {
    return (
      <AppShell>
        <p className="text-xs text-red-500">Payment not found</p>
      </AppShell>
    );
  }

  // Extract specific audit entries
  const evalLog = auditLogs?.find((a) => a.event_type === "PAYMENT_EVALUATED");
  const execLog = auditLogs?.find((a) => a.event_type === "PAYMENT_EXECUTED");

  const agentAssessment = evalLog?.detail?.agent_assessment as
    | Record<string, unknown>
    | undefined;
  const triggeredRules = (evalLog?.detail?.triggered_rules as unknown[]) ?? [];
  const riskSignals = (evalLog?.detail?.risk_signals as unknown[]) ?? [];
  const escalated = evalLog?.detail?.escalated_by_agent as boolean | undefined;

  return (
    <AppShell>
      {/* Back */}
      <Link href="/payments" className="mb-4 inline-block">
        <Button variant="ghost" size="sm">
          <ArrowLeft className="h-3.5 w-3.5 mr-1" /> Back
        </Button>
      </Link>

      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <h1 className="text-xl font-semibold text-neutral-900">
          {formatCurrency(payment.amount, payment.currency)}
        </h1>
        <Badge status={payment.status}>{payment.status}</Badge>
        {escalated && (
          <Badge status="BLOCKED">
            <AlertTriangle className="mr-1 h-3 w-3" />
            Agent Escalated
          </Badge>
        )}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {/* Payment Info */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CreditCard className="h-4 w-4 text-neutral-400" />
              Payment Details
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2.5 text-sm">
            <Row label="ID" value={payment.id} mono />
            <Row label="Vendor" value={payment.vendor_id} mono />
            <Row label="Amount" value={formatCurrency(payment.amount, payment.currency)} />
            <Row label="Category" value={payment.category ?? "—"} />
            <Row label="Description" value={payment.description ?? "—"} />
            <Row label="Invoice Ref" value={payment.invoice_ref ?? "—"} />
            <Row label="Idempotency Key" value={payment.idempotency_key} mono />
            <Row label="Created" value={formatDate(payment.created_at)} />
          </CardContent>
        </Card>

        {/* Policy Evaluation */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-neutral-400" />
              Policy Evaluation
            </CardTitle>
          </CardHeader>
          <CardContent>
            {evalLog ? (
              <div className="space-y-3">
                <div className="flex gap-3 text-sm">
                  <span className="text-neutral-400">Policy Verdict:</span>
                  <Badge status={evalLog.detail.policy_verdict as string}>
                    {evalLog.detail.policy_verdict as string}
                  </Badge>
                </div>
                <div className="flex gap-3 text-sm">
                  <span className="text-neutral-400">Final Verdict:</span>
                  <Badge status={evalLog.detail.final_verdict as string}>
                    {evalLog.detail.final_verdict as string}
                  </Badge>
                </div>
                {triggeredRules.length > 0 && (
                  <div>
                    <p className="mb-1.5 text-[11px] font-medium text-neutral-400 uppercase tracking-wide">
                      Triggered Rules
                    </p>
                    <div className="space-y-1.5">
                      {triggeredRules.map((r: unknown, i: number) => {
                        const rule = r as Record<string, string>;
                        return (
                          <div
                            key={i}
                            className="rounded-lg bg-neutral-50 p-2.5 text-xs"
                          >
                            <span className="font-medium text-neutral-900">
                              {rule.rule_name}
                            </span>{" "}
                            <span className="text-neutral-400">({rule.rule_type})</span> —{" "}
                            <span className="text-neutral-500">
                              {rule.detail}
                            </span>{" "}
                            → <Badge status={rule.verdict}>{rule.verdict}</Badge>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
                {triggeredRules.length === 0 && (
                  <p className="text-xs text-neutral-400">
                    No rules triggered — all clear
                  </p>
                )}
              </div>
            ) : (
              <p className="text-xs text-neutral-400">
                No evaluation data available
              </p>
            )}
          </CardContent>
        </Card>

        {/* Agent Reasoning */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-neutral-400" />
              Agent Reasoning
            </CardTitle>
          </CardHeader>
          <CardContent>
            {agentAssessment ? (
              <div className="space-y-3">
                <div className="flex items-center gap-4 text-sm">
                  <span className="text-neutral-400">Risk Score:</span>
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 w-20 rounded-full bg-neutral-100">
                      <div
                        className={`h-1.5 rounded-full ${(agentAssessment.risk_score as number) > 60
                            ? "bg-red-400"
                            : (agentAssessment.risk_score as number) > 30
                              ? "bg-amber-400"
                              : "bg-emerald-400"
                          }`}
                        style={{
                          width: `${agentAssessment.risk_score}%`,
                        }}
                      />
                    </div>
                    <span className="text-xs font-medium text-neutral-700">
                      {agentAssessment.risk_score as number}/100
                    </span>
                  </div>
                </div>
                <div className="text-sm">
                  <span className="text-neutral-400">Explanation:</span>
                  <p className="mt-1 text-xs text-neutral-600 leading-relaxed">
                    {agentAssessment.risk_explanation as string}
                  </p>
                </div>
                <div className="text-sm">
                  <span className="text-neutral-400">Should Escalate:</span>{" "}
                  <span className="text-xs font-medium text-neutral-700">
                    {agentAssessment.should_escalate ? "Yes" : "No"}
                  </span>
                </div>
                <div className="text-sm">
                  <span className="text-neutral-400">Confidence:</span>{" "}
                  <span className="text-xs font-medium text-neutral-700">
                    {((agentAssessment.confidence as number) * 100).toFixed(0)}%
                  </span>
                </div>
                {(agentAssessment.suspicious_patterns as string[])?.length >
                  0 && (
                    <div>
                      <p className="text-[11px] text-neutral-400 mb-1.5 uppercase tracking-wide font-medium">
                        Suspicious Patterns
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {(agentAssessment.suspicious_patterns as string[]).map(
                          (p, i) => (
                            <span
                              key={i}
                              className="rounded-full bg-red-50 px-2 py-0.5 text-[11px] text-red-500"
                            >
                              {p}
                            </span>
                          )
                        )}
                      </div>
                    </div>
                  )}
              </div>
            ) : (
              <p className="text-xs text-neutral-400">
                No agent analysis available
              </p>
            )}

            {/* Risk signals */}
            {riskSignals.length > 0 && (
              <div className="mt-4 border-t border-neutral-100 pt-3">
                <p className="mb-2 text-[11px] font-medium text-neutral-400 uppercase tracking-wide">
                  Risk Signals
                </p>
                <div className="space-y-1">
                  {riskSignals.map((s: unknown, i: number) => {
                    const sig = s as Record<string, string>;
                    return (
                      <div
                        key={i}
                        className={`rounded-lg px-2.5 py-1.5 text-xs ${sig.severity === "high"
                            ? "bg-red-50 text-red-500"
                            : sig.severity === "medium"
                              ? "bg-amber-50 text-amber-500"
                              : "bg-neutral-50 text-neutral-500"
                          }`}
                      >
                        <span className="font-medium">{sig.signal}</span>:{" "}
                        {sig.detail}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Audit Timeline */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-neutral-400" />
              Audit Timeline
            </CardTitle>
          </CardHeader>
          <CardContent>
            {auditLogs && auditLogs.length > 0 ? (
              <div className="space-y-3">
                {[...auditLogs].reverse().map((log) => (
                  <div
                    key={log.id}
                    className="border-l-2 border-neutral-200 pl-4 pb-3"
                  >
                    <div className="flex items-center gap-2">
                      <Badge
                        status={
                          log.event_type.includes("BLOCK")
                            ? "BLOCKED"
                            : log.event_type.includes("FAIL")
                              ? "FAILED"
                              : log.event_type.includes("EXECUTED")
                                ? "COMPLETED"
                                : "PENDING"
                        }
                      >
                        {log.event_type}
                      </Badge>
                      <span className="text-[11px] text-neutral-400">
                        {formatDate(log.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-neutral-400">
                      Actor: {log.actor}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-neutral-400">No audit entries</p>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex justify-between">
      <span className="text-neutral-400">{label}</span>
      <span className={mono ? "font-mono text-xs text-neutral-600" : "text-neutral-700"}>
        {value}
      </span>
    </div>
  );
}
