import { NextRequest, NextResponse } from "next/server";
import { allocateMemory } from "@/lib/gRPC_Client";
import prisma from "@/lib/prisma";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { tenant_id, size_mb } = body;

    if (!tenant_id || typeof tenant_id !== "string") {
      return NextResponse.json(
        { error: "tenant_id is required" },
        { status: 400 }
      );
    }

    const sizeMb = Number(size_mb);
    if (!sizeMb || sizeMb < 1 || sizeMb > 512) {
      return NextResponse.json(
        { error: "size_mb must be between 1 and 512" },
        { status: 400 }
      );
    }

    console.log(`[/api/allocate] Request: tenant_id=${tenant_id} size_mb=${sizeMb}`);

    // Verify the tenant exists
    const tenant = await prisma.tenant.findUnique({
      where: { tenant_id },
      select: { tenant_id: true, name: true },
    });

    if (!tenant) {
      console.log(`[/api/allocate] Tenant NOT FOUND: ${tenant_id}`);
      return NextResponse.json(
        { error: "Tenant not found. Register it first at /tenants." },
        { status: 404 }
      );
    }

    console.log(`[/api/allocate] Tenant found: ${tenant.name} (${tenant.tenant_id})`);

    const sizeBytes = sizeMb * 1024 * 1024;

    // Call C++ backend via gRPC
    const result = await allocateMemory({
      tenantId: tenant.tenant_id,
      sizeBytes,
    });

    // Verify allocation was persisted by the C++ server
    const dbRecord = await prisma.memoryallocation.findUnique({
      where: { allocation_id: result.allocationId },
      select: { allocation_id: true, state: true },
    });

    return NextResponse.json({
      allocation_id: result.allocationId,
      shm_key: result.shmKey,
      offset: result.offset,
      size_bytes: sizeBytes,
      tenant_name: tenant.name,
      db_confirmed: !!dbRecord,
      db_state: dbRecord?.state ?? "pending",
    });
  } catch (err: any) {
    console.error("[/api/allocate] Error:", err.message);
    return NextResponse.json(
      { error: err.message || "Internal server error" },
      { status: 502 }
    );
  }
}