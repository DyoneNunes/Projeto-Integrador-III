"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Loader2, CheckCircle2, Copy } from "lucide-react";

interface CreatedTenant {
  tenant_id: string;
  name: string;
  api_key: string;
}

export default function TenantForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [created, setCreated] = useState<CreatedTenant | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setCreated(null);

    try {
      const res = await fetch("/api/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Failed to create tenant");
      }

      setCreated(data);
      setName("");
      router.refresh();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function copyKey() {
    if (!created) return;
    navigator.clipboard.writeText(created.api_key);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Tenant name (e.g. lab-01, derek-dev)"
          className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
          required
        />
        <button
          type="submit"
          disabled={loading || !name.trim()}
          className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:bg-violet-800 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Create Tenant
        </button>
      </form>

      {error && (
        <div className="px-4 py-3 bg-red-950 border border-red-800 rounded-lg text-red-200 text-sm">
          {error}
        </div>
      )}

      {created && (
        <div className="px-4 py-4 bg-emerald-950 border border-emerald-800 rounded-lg space-y-2">
          <div className="flex items-center gap-2 text-emerald-300 text-sm font-medium">
            <CheckCircle2 className="h-4 w-4" />
            Tenant &quot;{created.name}&quot; created successfully
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 px-3 py-2 bg-gray-900 border border-gray-700 rounded font-mono text-xs text-amber-400 select-all">
              {created.api_key}
            </code>
            <button
              onClick={copyKey}
              className="flex items-center gap-1.5 px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded text-xs text-white transition-colors"
            >
              <Copy className="h-3.5 w-3.5" />
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <p className="text-xs text-emerald-400/70">
            Save this key now — it will not be shown in full again.
          </p>
        </div>
      )}
    </div>
  );
}