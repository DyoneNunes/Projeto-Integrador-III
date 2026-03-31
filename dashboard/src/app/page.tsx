import {
  HardDrive,
  Users,
  HeartPulse,
  MemoryStick,
  BarChart3,
  Key,
} from "lucide-react";
import Link from "next/link";
import prisma from "@/lib/prisma";
import AllocateModal from "@/components/AllocateModal";
import TopTenantsChart from "@/components/TopTenantsChart";
import RefreshButton from "@/components/RefreshButton";
import AutoRefresh from "@/components/AutoRefresh";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function stateColor(state: string): string {
  switch (state) {
    case "active":
      return "text-emerald-400 bg-emerald-400/10 border-emerald-400/20";
    case "provisioning":
      return "text-amber-400 bg-amber-400/10 border-amber-400/20";
    case "releasing":
      return "text-orange-400 bg-orange-400/10 border-orange-400/20";
    case "released":
      return "text-gray-500 bg-gray-500/10 border-gray-500/20";
    case "failed":
      return "text-red-400 bg-red-400/10 border-red-400/20";
    default:
      return "text-gray-400 bg-gray-400/10 border-gray-400/20";
  }
}

async function getStats() {
  try {
    const [ramAgg, tenantCount] = await Promise.all([
      prisma.memoryallocation.aggregate({
        _sum: { size_bytes: true },
        where: { state: "active" },
      }),
      prisma.memoryallocation.findMany({
        where: { state: "active" },
        distinct: ["tenant_id"],
        select: { tenant_id: true },
      }),
    ]);
    return {
      total_ram: Number(ramAgg._sum.size_bytes ?? 0),
      active_tenants: tenantCount.length,
      db_healthy: true,
    };
  } catch {
    return { total_ram: 0, active_tenants: 0, db_healthy: false };
  }
}

async function getAllocations() {
  try {
    const rows = await prisma.memoryallocation.findMany({
      include: { tenant: { select: { name: true } } },
      orderBy: { created_at: "desc" },
      take: 50,
    });
    return rows.map((r) => ({
      allocation_id: r.allocation_id,
      tenant_name: r.tenant?.name ?? "unknown",
      size_bytes: Number(r.size_bytes),
      shm_key: r.shm_key,
      state: r.state ?? "unknown",
      created_at: r.created_at?.toISOString() ?? "",
    }));
  } catch {
    return [];
  }
}

async function getTopTenants() {
  try {
    const rows = await prisma.memoryallocation.groupBy({
      by: ["tenant_id"],
      where: { state: "active" },
      _sum: { size_bytes: true },
      orderBy: { _sum: { size_bytes: "desc" } },
      take: 5,
    });

    const tenantIds = rows.map((r) => r.tenant_id);
    const tenants = await prisma.tenant.findMany({
      where: { tenant_id: { in: tenantIds } },
      select: { tenant_id: true, name: true },
    });
    const nameMap = new Map(tenants.map((t) => [t.tenant_id, t.name]));

    return rows.map((r) => ({
      tenant_name: nameMap.get(r.tenant_id) ?? r.tenant_id.slice(0, 8),
      total_bytes: Number(r._sum.size_bytes ?? 0),
    }));
  } catch {
    return [];
  }
}

export default async function DashboardPage() {
  const [stats, allocations, topTenants] = await Promise.all([
    getStats(),
    getAllocations(),
    getTopTenants(),
  ]);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Auto-refresh every 5s */}
      <AutoRefresh intervalMs={5000} />

      {/* Header */}
      <header className="mb-8 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <MemoryStick className="h-8 w-8 text-violet-400" />
            <h1 className="text-2xl font-bold tracking-tight">
              MaaS Dashboard
            </h1>
          </div>
          <p className="text-gray-500 text-sm">
            Memory as a Service — Real-time Allocation Monitor
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/tenants"
            className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <Key className="h-4 w-4 text-amber-400" />
            Tenants
          </Link>
          <AllocateModal />
        </div>
      </header>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        {/* Total RAM */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-gray-400 text-sm font-medium">
              Total RAM Allocated
            </span>
            <HardDrive className="h-5 w-5 text-violet-400" />
          </div>
          <p className="text-3xl font-bold text-white">
            {formatBytes(stats.total_ram)}
          </p>
          <p className="text-xs text-gray-500 mt-1">Active allocations only</p>
        </div>

        {/* Active Tenants */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-gray-400 text-sm font-medium">
              Active Tenants
            </span>
            <Users className="h-5 w-5 text-sky-400" />
          </div>
          <p className="text-3xl font-bold text-white">
            {stats.active_tenants}
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Unique tenants with active segments
          </p>
        </div>

        {/* System Health */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-gray-400 text-sm font-medium">
              System Health
            </span>
            <HeartPulse className="h-5 w-5 text-emerald-400" />
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span
              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium border ${
                stats.db_healthy
                  ? "text-emerald-400 bg-emerald-400/10 border-emerald-400/20"
                  : "text-red-400 bg-red-400/10 border-red-400/20"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  stats.db_healthy
                    ? "bg-emerald-400 animate-pulse"
                    : "bg-red-400"
                }`}
              />
              {stats.db_healthy ? "PostgreSQL Connected" : "Database Offline"}
            </span>
          </div>
          <p className="text-xs text-gray-500 mt-3">
            Database connectivity status
          </p>
        </div>
      </div>

      {/* Insights — Top Tenants Chart */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-8">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="h-5 w-5 text-violet-400" />
          <h2 className="text-lg font-semibold">
            Top Tenants by Active Memory
          </h2>
        </div>
        <TopTenantsChart data={topTenants} />
      </div>

      {/* Allocation Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold">Memory Allocations</h2>
          <RefreshButton />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-gray-400">
                <th className="text-left px-5 py-3 font-medium">ID</th>
                <th className="text-left px-5 py-3 font-medium">Tenant</th>
                <th className="text-left px-5 py-3 font-medium">Size</th>
                <th className="text-left px-5 py-3 font-medium">SHM Key</th>
                <th className="text-left px-5 py-3 font-medium">State</th>
                <th className="text-left px-5 py-3 font-medium">Created At</th>
              </tr>
            </thead>
            <tbody>
              {allocations.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-5 py-12 text-center text-gray-600"
                  >
                    No allocations found. Start the MaaS C++ server and allocate
                    memory to see data here.
                  </td>
                </tr>
              ) : (
                allocations.map((a) => (
                  <tr
                    key={a.allocation_id}
                    className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors"
                  >
                    <td className="px-5 py-3 font-mono text-xs text-gray-400">
                      {a.allocation_id.slice(0, 8)}...
                    </td>
                    <td className="px-5 py-3 text-white">{a.tenant_name}</td>
                    <td className="px-5 py-3 text-gray-300">
                      {formatBytes(a.size_bytes)}
                    </td>
                    <td className="px-5 py-3">
                      <code className="font-mono text-xs text-violet-400 bg-violet-400/10 px-2 py-0.5 rounded">
                        {a.shm_key}
                      </code>
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium border ${stateColor(
                          a.state
                        )}`}
                      >
                        {a.state}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-gray-400 text-xs">
                      {new Date(a.created_at).toLocaleString("pt-BR", {
                        timeZone: "America/Sao_Paulo",
                      })}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Footer */}
      <footer className="mt-8 text-center text-xs text-gray-600">
        MaaS — PI-III 5&ordm; Per&iacute;odo TADS FAESA &bull; Dyone Andrade
      </footer>
    </div>
  );
}