"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

type Policy = {
  id: string;
  name: string;
  rule_type: string;
  parameters: Record<string, unknown>;
  priority: number;
  is_active: boolean;
  created_at: string;
};

const RULE_TYPES = [
  "MAX_TXN",
  "DAILY_CAP",
  "MONTHLY_CAP",
  "VELOCITY",
  "CATEGORY_BUDGET",
  "VENDOR_ALLOWLIST",
  "APPROVAL_THRESHOLD",
];

export default function PoliciesPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "",
    rule_type: "MAX_TXN",
    parameters: "{}",
    priority: "0",
  });

  const { data: policies, isLoading } = useQuery<Policy[]>({
    queryKey: ["policies"],
    queryFn: () => api.get("/policies"),
  });

  const createMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/policies", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["policies"] });
      setShowForm(false);
    },
  });

  const toggleMut = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      api.patch(`/policies/${id}`, { is_active: !is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["policies"] }),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    let params: Record<string, unknown>;
    try {
      params = JSON.parse(form.parameters);
    } catch {
      alert("Invalid JSON in parameters");
      return;
    }
    createMut.mutate({
      name: form.name,
      rule_type: form.rule_type,
      parameters: params,
      priority: Number(form.priority),
    });
  };

  return (
    <AppShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-neutral-900">Policies</h1>
          <p className="text-xs text-neutral-400 mt-1">
            Configure payment guardrails
          </p>
        </div>
        <Button size="sm" onClick={() => setShowForm(!showForm)}>
          <Plus className="h-3.5 w-3.5" /> Add Policy
        </Button>
      </div>

      {showForm && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>New Policy</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="grid gap-3 sm:grid-cols-2">
              <Input
                placeholder="Policy name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
              <select
                className="rounded-lg border border-neutral-200 px-3 py-2 text-xs text-neutral-700 focus:outline-none focus:ring-2 focus:ring-neutral-900"
                value={form.rule_type}
                onChange={(e) =>
                  setForm({ ...form, rule_type: e.target.value })
                }
              >
                {RULE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <Input
                placeholder='Parameters JSON, e.g. {"max_amount": 5000}'
                value={form.parameters}
                onChange={(e) =>
                  setForm({ ...form, parameters: e.target.value })
                }
              />
              <Input
                placeholder="Priority (higher = checked first)"
                type="number"
                value={form.priority}
                onChange={(e) =>
                  setForm({ ...form, priority: e.target.value })
                }
              />
              <div className="sm:col-span-2 flex gap-2">
                <Button type="submit" size="sm" disabled={createMut.isPending}>
                  Create
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setShowForm(false)}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {isLoading && <p className="text-xs text-neutral-400">Loading...</p>}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {policies?.map((p) => (
          <Card key={p.id}>
            <CardContent className="pt-5">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm font-medium text-neutral-900">
                  {p.name}
                </span>
                <Badge status={p.is_active ? "ACTIVE" : "BLOCKED"}>
                  {p.is_active ? "Active" : "Disabled"}
                </Badge>
              </div>
              <div className="mb-3 space-y-1 text-xs text-neutral-400">
                <p>
                  Type: <span className="text-neutral-600">{p.rule_type}</span>
                </p>
                <p>
                  Priority: <span className="text-neutral-600">{p.priority}</span>
                </p>
                <p className="mt-1.5">Params:</p>
                <pre className="mt-1 rounded-lg bg-neutral-50 p-2.5 text-[11px] text-neutral-600 font-mono">
                  {JSON.stringify(p.parameters, null, 2)}
                </pre>
              </div>
              <Button
                size="sm"
                variant={p.is_active ? "outline" : "default"}
                onClick={() =>
                  toggleMut.mutate({ id: p.id, is_active: p.is_active })
                }
              >
                {p.is_active ? "Disable" : "Enable"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </AppShell>
  );
}
