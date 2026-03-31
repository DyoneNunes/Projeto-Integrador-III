import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import path from "path";

export interface AllocateRequest {
  tenantId: string;
  sizeBytes: number;
}

export interface AllocateResponse {
  allocationId: string;
  shmKey: string;
  offset: string;
}

let _client: any = null;

function getClient() {
  if (_client) return _client;

  // In Docker the proto is mounted at /app/proto; locally it's at ../proto
  const PROTO_PATH =
    process.env.PROTO_PATH ||
    path.resolve(process.cwd(), "proto", "maas.proto");

  const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
    keepCase: false,
    longs: String,
    enums: String,
    defaults: true,
    oneofs: true,
  });

  const maasProto = grpc.loadPackageDefinition(packageDefinition) as any;
  const host = process.env.MAAS_CORE_HOST || "maas-core:50051";

  _client = new maasProto.maas.MemoryService(
    host,
    grpc.credentials.createInsecure()
  );

  return _client;
}

export function allocateMemory(
  req: AllocateRequest
): Promise<AllocateResponse> {
  return new Promise((resolve, reject) => {
    const client = getClient();
    console.log(`[gRPC] Allocate request: tenantId=${req.tenantId} sizeBytes=${req.sizeBytes}`);
    client.Allocate(
      { tenantId: req.tenantId, sizeBytes: req.sizeBytes },
      { deadline: Date.now() + 10_000 },
      (err: grpc.ServiceError | null, response: any) => {
        if (err) {
          reject(new Error(`gRPC error (${err.code}): ${err.details}`));
          return;
        }
        console.log(`[gRPC] Allocate response:`, JSON.stringify(response));
        resolve({
          allocationId: response.allocationId,
          shmKey: response.shmKey,
          offset: response.offset,
        });
      }
    );
  });
}