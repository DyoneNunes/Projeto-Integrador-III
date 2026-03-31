"use client";

import { useState } from "react";
import { Copy, Check, Key, ShieldCheck, ShieldOff } from "lucide-react";

interface Tenant {
  tenant_id: string;
  name: string;
  plan: string;
  status: string;
  api_key: string | null;
  created_at: string;
  active_allocations: number;
}

function maskKey(key: string): string {
  if (key.length <= 16) return key;
  return key.slice(0, 14) + "..." + key.slice(-4);
}

export default function TenantList({ tenants }: { tenants: Tenant[] }) {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  function copyKey(tenantId: string, key: string) {
    navigator.clipboard.writeText(key);
    setCopiedId(tenantId);
    setTimeout(() => setCopiedId(null), 2000);
  }

  if (tenants.length === 0) {
    return (
      <div className="px-5 py-12 text-center text-gray-600 text-sm">
        No tenants registered yet. Create one above to get started.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-gray-400">
            <th className="text-left px-5 py-3 font-medium">Name</th>
            <th className="text-left px-5 py-3 font-medium">Plan</th>
            <th className="text-left px-5 py-3 font-medium">API Key</th>
            <th className="text-left px-5 py-3 font-medium">Active Allocs</th>
            <th className="text-left px-5 py-3 font-medium">Status</th>
            <th className="text-left px-5 py-3 font-medium">Created</th>
          </tr>
        </thead>
        <tbody>
          {tenants.map((t) => (
            <tr
              key={t.tenant_id}
              className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
            >
              <td className="px-5 py-3 text-white font-medium">{t.name}</td>
              <td className="px-5 py-3">
                <span className="px-2 py-0.5 rounded-full text-xs font-medium border text-violet-400 bg-violet-400/10 border-violet-400/20">
                  {t.plan}
                </span>
              </td>
              <td className="px-5 py-3">
                {t.api_key ? (
                  <div className="flex items-center gap-2">
                    <code className="font-mono text-xs text-amber-400 bg-amber-400/10 px-2 py-0.5 rounded">
                      {maskKey(t.api_key)}
                    </code>
                    <button
                      onClick={() => copyKey(t.tenant_id, t.api_key!)}
                      className="text-gray-400 hover:text-white transition-colors"
                      title="Copy full key"
                    >
                      {copiedId === t.tenant_id ? (
                        <Check className="h-3.5 w-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </div>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-gray-600">
                    <Key className="h-3 w-3" />
                    No key
                  </span>
                )}
              </td>
              <td className="px-5 py-3 text-gray-300">
                {t.active_allocations}
              </td>
              <td className="px-5 py-3">
                <span
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${
                    t.status === "active"
                      ? "text-emerald-400 bg-emerald-400/10 border-emerald-400/20"
                      : "text-red-400 bg-red-400/10 border-red-400/20"
                  }`}
                >
                  {t.status === "active" ? (
                    <ShieldCheck className="h-3 w-3" />
                  ) : (
                    <ShieldOff className="h-3 w-3" />
                  )}
                  {t.status}
                </span>
              </td>
              <td className="px-5 py-3 text-gray-400 text-xs">
                {t.created_at
                  ? new Date(t.created_at).toLocaleString("pt-BR", {
                      timeZone: "America/Sao_Paulo",
                    })
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}