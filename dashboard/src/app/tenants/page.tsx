import { Users, Key, MemoryStick, ArrowLeft } from "lucide-react";
import prisma from "@/lib/prisma";
import TenantForm from "@/components/TenantForm";
import TenantList from "@/components/TenantList";
import Link from "next/link";

export const dynamic = "force-dynamic";

async function getTenants() {
  try {
    const tenants = await prisma.tenant.findMany({
      orderBy: { created_at: "desc" },
      select: {
        tenant_id: true,
        name: true,
        plan: true,
        status: true,
        api_key: true,
        created_at: true,
        _count: {
          select: { memoryallocation: { where: { state: "active" } } },
        },
      },
    });
    return tenants.map((t) => ({
      tenant_id: t.tenant_id,
      name: t.name,
      plan: t.plan,
      status: t.status ?? "active",
      api_key: t.api_key ?? null,
      created_at: t.created_at?.toISOString() ?? "",
      active_allocations: t._count.memoryallocation,
    }));
  } catch {
    return [];
  }
}

export default async function TenantsPage() {
  const tenants = await getTenants();

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <header className="mb-8">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-gray-400 hover:text-white transition-colors mb-4"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>
        <div className="flex items-center gap-3 mb-1">
          <Users className="h-8 w-8 text-violet-400" />
          <h1 className="text-2xl font-bold tracking-tight">
            Tenant Management
          </h1>
        </div>
        <p className="text-gray-500 text-sm">
          Register tenants and generate API keys for memory access control.
        </p>
      </header>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm font-medium">
              Registered Tenants
            </span>
            <Users className="h-5 w-5 text-sky-400" />
          </div>
          <p className="text-3xl font-bold text-white">{tenants.length}</p>
        </div>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-2">
            <span className="text-gray-400 text-sm font-medium">
              Active API Keys
            </span>
            <Key className="h-5 w-5 text-amber-400" />
          </div>
          <p className="text-3xl font-bold text-white">
            {tenants.filter((t) => t.api_key).length}
          </p>
        </div>
      </div>

      {/* Create Tenant Form */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-8">
        <div className="flex items-center gap-2 mb-4">
          <MemoryStick className="h-5 w-5 text-violet-400" />
          <h2 className="text-lg font-semibold">Register New Tenant</h2>
        </div>
        <TenantForm />
      </div>

      {/* Tenant List */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold">All Tenants</h2>
        </div>
        <TenantList tenants={tenants} />
      </div>
    </div>
  );
}