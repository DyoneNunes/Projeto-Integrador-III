import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/prisma";

export const dynamic = "force-dynamic";

/**
 * GET /api/report?from=YYYY-MM-DD&to=YYYY-MM-DD
 *
 * Relatório de consumo de memória no período: soma de size_bytes das
 * alocações criadas entre `from` e `to`, com quebra por tenant e por mês.
 * Sem datas, assume o mês corrente.
 */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const fromParam = searchParams.get("from");
    const toParam = searchParams.get("to");

    const now = new Date();
    // Default: do primeiro dia do mês corrente até agora.
    const defaultFrom = new Date(now.getFullYear(), now.getMonth(), 1);

    const from = fromParam ? new Date(`${fromParam}T00:00:00`) : defaultFrom;
    // Inclui o dia inteiro do `to` (até 23:59:59.999).
    const to = toParam
      ? new Date(`${toParam}T23:59:59.999`)
      : now;

    if (isNaN(from.getTime()) || isNaN(to.getTime())) {
      return NextResponse.json(
        { error: "Datas inválidas. Use o formato YYYY-MM-DD." },
        { status: 400 }
      );
    }
    if (from > to) {
      return NextResponse.json(
        { error: "A data inicial deve ser anterior à data final." },
        { status: 400 }
      );
    }

    const where = { created_at: { gte: from, lte: to } } as const;

    const [byTenantRaw, totals, byMonthRaw, allocRows] = await Promise.all([
      // Total por tenant no período.
      prisma.memoryallocation.groupBy({
        by: ["tenant_id"],
        where,
        _sum: { size_bytes: true },
        _count: true,
        orderBy: { _sum: { size_bytes: "desc" } },
      }),
      // Totais gerais do período.
      prisma.memoryallocation.aggregate({
        where,
        _sum: { size_bytes: true },
        _count: true,
      }),
      // Evolução mês a mês (date_trunc no Postgres).
      prisma.$queryRaw<{ month: Date; total_bytes: bigint | null; count: bigint }[]>`
        SELECT date_trunc('month', created_at) AS month,
               SUM(size_bytes) AS total_bytes,
               COUNT(*) AS count
        FROM memoryallocation
        WHERE created_at >= ${from} AND created_at <= ${to}
        GROUP BY 1
        ORDER BY 1 ASC
      `,
      // Lista detalhada de alocações do período (para o relatório PDF).
      prisma.memoryallocation.findMany({
        where,
        include: { tenant: { select: { name: true } } },
        orderBy: { created_at: "desc" },
        take: 1000,
      }),
    ]);

    // Resolve nomes dos tenants.
    const tenantIds = byTenantRaw.map((r) => r.tenant_id);
    const tenants = await prisma.tenant.findMany({
      where: { tenant_id: { in: tenantIds } },
      select: { tenant_id: true, name: true },
    });
    const nameMap = new Map(tenants.map((t) => [t.tenant_id, t.name]));

    const by_tenant = byTenantRaw.map((r) => ({
      tenant_id: r.tenant_id,
      tenant_name: nameMap.get(r.tenant_id) ?? r.tenant_id.slice(0, 8),
      total_bytes: Number(r._sum.size_bytes ?? 0),
      allocations: r._count,
    }));

    const by_month = byMonthRaw.map((r) => {
      const d = new Date(r.month);
      return {
        month: `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`,
        total_bytes: Number(r.total_bytes ?? 0),
        allocations: Number(r.count),
      };
    });

    const allocations = allocRows.map((a) => ({
      allocation_id: a.allocation_id,
      tenant_name: a.tenant?.name ?? "unknown",
      size_bytes: Number(a.size_bytes),
      shm_key: a.shm_key,
      state: a.state ?? "unknown",
      created_at: a.created_at?.toISOString() ?? "",
    }));

    return NextResponse.json({
      period: { from: from.toISOString(), to: to.toISOString() },
      totals: {
        total_bytes: Number(totals._sum.size_bytes ?? 0),
        allocations: totals._count,
      },
      by_tenant,
      by_month,
      allocations,
    });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || "Falha ao gerar relatório" },
      { status: 500 }
    );
  }
}
