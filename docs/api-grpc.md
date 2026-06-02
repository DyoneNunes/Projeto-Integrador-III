# Contrato gRPC — `MemoryService`

A fonte da verdade é [`proto/maas.proto`](https://github.com/) (`package maas`). O Core implementa o serviço `MemoryService`; o Dashboard e os clientes Python carregam o mesmo `.proto`.

## RPCs

| RPC | Tipo | Entrada → Saída |
| :--- | :--- | :--- |
| `Allocate` | unário | `AllocateRequest` → `AllocateResponse` |
| `Deallocate` | unário | `DeallocateRequest` → `DeallocateResponse` |
| `WriteMemory` | unário | `WriteRequest` → `Acknowledge` |
| `ReadMemory` | unário | `ReadRequest` → `ReadResponse` |
| `ReportMetrics` | client-streaming | `stream MetricsReport` → `Acknowledge` |
| `CheckHealth` | unário | `Empty` → `HealthCheckResponse` |

## Mensagens

### Alocação
```proto
message AllocateRequest {
  string tenant_id  = 1;   // UUID do tenant
  int64  size_bytes = 2;   // tamanho do bloco
}
message AllocateResponse {
  string allocation_id = 1;  // UUID da alocação
  string shm_key       = 2;  // chave SHM do Linux (/maas_<uuid>)
  int64  offset        = 3;  // offset dentro da região (0 por bloco independente)
}

message DeallocateRequest  { string tenant_id = 1; string allocation_id = 2; }
message DeallocateResponse { bool success = 1; string message = 2; }
```

### I/O remoto
```proto
message WriteRequest {
  string tenant_id     = 1;
  string allocation_id = 2;
  int64  offset        = 3;
  bytes  data          = 4;   // payload binário (até ~64 MiB)
}
message ReadRequest {
  string tenant_id     = 1;
  string allocation_id = 2;
  int64  offset        = 3;
  int64  size_bytes    = 4;
}
message ReadResponse { bytes data = 1; }
```

### Métricas e saúde
```proto
message MetricsReport {
  string tenant_id     = 1;
  string allocation_id = 2;
  string node_id       = 3;
  int64  timestamp_us  = 4;
  double rtt_ms        = 5;
  double memory_pressure      = 6;  // [0.0, 1.0]
  double cache_hit_ratio      = 7;  // [0.0, 1.0]
  double net_bottleneck_score = 8;
}
message Acknowledge { int64 metrics_received = 1; string message = 2; }

message Empty {}
message HealthCheckResponse { string status = 1; }   // "SERVING"
```

## Códigos de erro relevantes

| Situação | `grpc::StatusCode` |
| :--- | :--- |
| `tenant_id`/`size_bytes` inválidos | `INVALID_ARGUMENT` |
| Capacidade da arena esgotada | `RESOURCE_EXHAUSTED` |
| Alocação inexistente no `Deallocate` | `NOT_FOUND` |
| `offset + len` fora dos limites no Write/Read | `OUT_OF_RANGE` |
| Falha ao persistir no banco | `INTERNAL` |

## Exemplo — Python

```python
import grpc, maas_pb2, maas_pb2_grpc

channel = grpc.insecure_channel("localhost:50051")
stub = maas_pb2_grpc.MemoryServiceStub(channel)

# 1) Alocar 1 MiB
resp = stub.Allocate(maas_pb2.AllocateRequest(tenant_id="meu-app", size_bytes=1048576))
print("shm_key:", resp.shm_key, "alloc:", resp.allocation_id)

# 2a) I/O remoto (cliente em outra máquina)
stub.WriteMemory(maas_pb2.WriteRequest(
    tenant_id="meu-app", allocation_id=resp.allocation_id, offset=0, data=b"Ola MaaS"))
data = stub.ReadMemory(maas_pb2.ReadRequest(
    tenant_id="meu-app", allocation_id=resp.allocation_id, offset=0, size_bytes=8)).data

# 3) Liberar
stub.Deallocate(maas_pb2.DeallocateRequest(
    tenant_id="meu-app", allocation_id=resp.allocation_id))
```

Para acesso local de altíssima velocidade (mesma máquina), use a `shm_key` com `posix_ipc` + `mmap` — veja o [Manual do Usuário](guias/manual-usuario.md).

## Coleções prontas

- `postman_maas_grpc.json`
- `insomnia_maas_grpc.json`
- Scripts em `scripts/` (`maas_writer.py`, `maas_reader.py`, `client_test.py`).
