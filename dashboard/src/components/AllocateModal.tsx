"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Plus, X, Loader2, MemoryStick } from "lucide-react";

interface AllocateResult {
  allocation_id: string;
  shm_key: string;
  size_bytes: number;
  db_confirmed: boolean;
}

interface TenantOption {
  tenant_id: string;
  name: string;
}

export default function AllocateModal() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [tenants, setTenants] = useState<TenantOption[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [sizeMb, setSizeMb] = useState(10);
  const [toast, setToast] = useState<{
    type: "success" | "error";
    message: string;
    shmKey?: string;
  } | null>(null);

  useEffect(() => {
    if (!open) return;
    fetch("/api/tenants")
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) {
          const mapped = data.map((t: any) => ({ tenant_id: t.tenant_id, name: t.name }));
          setTenants(mapped);
          // Always sync selection: pick current if still valid, else first
          const currentValid = mapped.some((t: TenantOption) => t.tenant_id === tenantId);
          if (!currentValid && mapped.length > 0) {
            setTenantId(mapped[0].tenant_id);
          }
        }
      })
      .catch(() => {});
  }, [open]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!tenantId) return;
    setLoading(true);
    setToast(null);

    try {
      const res = await fetch("/api/allocate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, size_mb: sizeMb }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Allocation failed");
      }

      const result = data as AllocateResult;
      const tenantName = tenants.find((t) => t.tenant_id === tenantId)?.name ?? tenantId.slice(0, 8);
      setToast({
        type: "success",
        message: `Allocated ${sizeMb} MB to "${tenantName}" — ID: ${result.allocation_id.slice(0, 8)}...`,
        shmKey: result.shm_key,
      });
      setOpen(false);
      setTimeout(() => router.refresh(), 1000);
    } catch (err: any) {
      setToast({
        type: "error",
        message: err.message || "Failed to allocate memory",
      });
    } finally {
      setLoading(false);
    }
  }

  const selectedName = tenants.find((t) => t.tenant_id === tenantId)?.name;

  return (
    <>
      {/* Trigger Button */}
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm font-medium rounded-lg transition-colors"
      >
        <Plus className="h-4 w-4" />
        Allocate Memory
      </button>

      {/* Toast Notification */}
      {toast && (
        <div className="fixed top-4 right-4 z-[60]">
          <div
            className={`flex items-start gap-3 px-4 py-3 rounded-lg border shadow-2xl max-w-md ${
              toast.type === "success"
                ? "bg-emerald-950 border-emerald-800 text-emerald-200"
                : "bg-red-950 border-red-800 text-red-200"
            }`}
          >
            <div className="flex-1">
              <p className="text-sm font-medium">{toast.message}</p>
              {toast.shmKey && (
                <p className="mt-1 text-xs font-mono opacity-80">
                  shm_key: {toast.shmKey}
                </p>
              )}
            </div>
            <button
              onClick={() => setToast(null)}
              className="text-current opacity-50 hover:opacity-100"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Modal Overlay */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />
          <div className="relative bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2">
                <MemoryStick className="h-5 w-5 text-violet-400" />
                <h3 className="text-lg font-semibold text-white">
                  Allocate Memory
                </h3>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-gray-400 hover:text-white transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-5">
              {/* Tenant Dropdown */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1.5">
                  Tenant
                </label>
                {tenants.length === 0 ? (
                  <div className="px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-gray-500 text-sm">
                    No tenants found.{" "}
                    <a href="/tenants" className="text-violet-400 underline">
                      Create one first
                    </a>
                  </div>
                ) : (
                  <select
                    value={tenantId}
                    onChange={(e) => setTenantId(e.target.value)}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-violet-500 focus:border-transparent"
                    required
                  >
                    {tenants.map((t) => (
                      <option key={t.tenant_id} value={t.tenant_id}>
                        {t.name} ({t.tenant_id.slice(0, 8)}...)
                      </option>
                    ))}
                  </select>
                )}
              </div>

              {/* Size Slider */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-sm font-medium text-gray-300">
                    Size
                  </label>
                  <span className="text-sm font-bold text-violet-400">
                    {sizeMb} MB
                  </span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={512}
                  value={sizeMb}
                  onChange={(e) => setSizeMb(Number(e.target.value))}
                  className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-violet-500"
                />
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>1 MB</span>
                  <span>512 MB</span>
                </div>
              </div>

              {/* Summary */}
              <div className="bg-gray-800/50 border border-gray-700/50 rounded-lg p-3">
                <p className="text-xs text-gray-400">
                  Allocating{" "}
                  <span className="text-white font-medium">
                    {(sizeMb * 1024 * 1024).toLocaleString()} bytes
                  </span>{" "}
                  to tenant{" "}
                  <span className="text-violet-400 font-medium">
                    {selectedName ?? "—"}
                  </span>{" "}
                  via{" "}
                  <code className="text-violet-400">MemoryService.Allocate</code>{" "}
                  gRPC.
                </p>
              </div>

              {/* Submit */}
              <button
                type="submit"
                disabled={loading || tenants.length === 0}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-violet-600 hover:bg-violet-500 disabled:bg-violet-800 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Allocating...
                  </>
                ) : (
                  <>
                    <Plus className="h-4 w-4" />
                    Allocate {sizeMb} MB
                  </>
                )}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}