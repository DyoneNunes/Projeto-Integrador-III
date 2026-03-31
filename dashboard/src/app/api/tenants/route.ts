import { NextRequest, NextResponse } from "next/server";
import { randomBytes } from "crypto";
import prisma from "@/lib/prisma";

function generateApiKey(): string {
  return `maas_live_${randomBytes(24).toString("hex")}`;
}

export async function GET() {
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
        _count: { select: { memoryallocation: { where: { state: "active" } } } },
      },
    });

    return NextResponse.json(tenants);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || "Failed to fetch tenants" },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { name } = body;

    if (!name || typeof name !== "string" || name.trim().length === 0) {
      return NextResponse.json(
        { error: "Tenant name is required" },
        { status: 400 }
      );
    }

    const apiKey = generateApiKey();

    const tenant = await prisma.tenant.create({
      data: {
        name: name.trim(),
        plan: "Developer",
        api_key: apiKey,
      },
    });

    return NextResponse.json({
      tenant_id: tenant.tenant_id,
      name: tenant.name,
      api_key: tenant.api_key,
      created_at: tenant.created_at,
    });
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || "Failed to create tenant" },
      { status: 500 }
    );
  }
}