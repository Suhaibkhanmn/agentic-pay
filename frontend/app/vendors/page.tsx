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
import { formatCurrency } from "@/lib/utils";

type Vendor = {
  id: string;
  name: string;
  external_id: string | null;
  category: string | null;
  status: string;
  daily_limit: number | null;
  monthly_limit: number | null;
  created_at: string;
};

export default function VendorsPage() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    name: "",
    category: "",
    daily_limit: "",
    monthly_limit: "",
  });

  const { data: vendors, isLoading } = useQuery<Vendor[]>({
    queryKey: ["vendors"],
    queryFn: () => api.get("/vendors"),
  });

  const createMut = useMutation({
    mutationFn: (body: Record<string, unknown>) => api.post("/vendors", body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendors"] });
      setShowForm(false);
      setForm({ name: "", category: "", daily_limit: "", monthly_limit: "" });
    },
  });

  const toggleStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.patch(`/vendors/${id}`, {
        status: status === "ACTIVE" ? "BLOCKED" : "ACTIVE",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendors"] }),
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    createMut.mutate({
      name: form.name,
      category: form.category || null,
      daily_limit: form.daily_limit ? Number(form.daily_limit) : null,
      monthly_limit: form.monthly_limit ? Number(form.monthly_limit) : null,
    });
  };

  return (
    <AppShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-neutral-900">Vendors</h1>
          <p className="text-xs text-neutral-400 mt-1">
            Manage vendor allowlist and limits
          </p>
        </div>
        <Button size="sm" onClick={() => setShowForm(!showForm)}>
          <Plus className="h-3.5 w-3.5" /> Add Vendor
        </Button>
      </div>

      {/* Create form */}
      {showForm && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>New Vendor</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="grid gap-3 sm:grid-cols-2">
              <Input
                placeholder="Vendor name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                required
              />
              <Input
                placeholder="Category"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              />
              <Input
                placeholder="Daily limit"
                type="number"
                value={form.daily_limit}
                onChange={(e) =>
                  setForm({ ...form, daily_limit: e.target.value })
                }
              />
              <Input
                placeholder="Monthly limit"
                type="number"
                value={form.monthly_limit}
                onChange={(e) =>
                  setForm({ ...form, monthly_limit: e.target.value })
                }
              />
              <div className="sm:col-span-2 flex gap-2">
                <Button type="submit" size="sm" disabled={createMut.isPending}>
                  {createMut.isPending ? "Creating..." : "Create"}
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

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-100 text-left text-[11px] font-medium text-neutral-400 uppercase tracking-wider">
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Category</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3">Daily Limit</th>
                  <th className="px-5 py-3">Monthly Limit</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-50">
                {isLoading && (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-xs text-neutral-400">
                      Loading...
                    </td>
                  </tr>
                )}
                {vendors?.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-xs text-neutral-400">
                      No vendors yet
                    </td>
                  </tr>
                )}
                {vendors?.map((v) => (
                  <tr key={v.id} className="hover:bg-neutral-50/50 transition-colors">
                    <td className="px-5 py-3 font-medium text-neutral-900">{v.name}</td>
                    <td className="px-5 py-3 text-neutral-500">
                      {v.category ?? "—"}
                    </td>
                    <td className="px-5 py-3">
                      <Badge status={v.status}>{v.status}</Badge>
                    </td>
                    <td className="px-5 py-3 text-neutral-500">
                      {v.daily_limit ? formatCurrency(v.daily_limit) : "—"}
                    </td>
                    <td className="px-5 py-3 text-neutral-500">
                      {v.monthly_limit ? formatCurrency(v.monthly_limit) : "—"}
                    </td>
                    <td className="px-5 py-3">
                      <Button
                        size="sm"
                        variant={v.status === "ACTIVE" ? "outline" : "default"}
                        onClick={() =>
                          toggleStatus.mutate({
                            id: v.id,
                            status: v.status,
                          })
                        }
                      >
                        {v.status === "ACTIVE" ? "Block" : "Activate"}
                      </Button>
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
