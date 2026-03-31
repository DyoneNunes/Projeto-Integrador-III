#!/usr/bin/env python3
"""
MaaS (Memory as a Service) — Cliente de teste gRPC
Conecta ao servidor em localhost:50051, aloca 10 MiB e exibe o resultado.

Uso:
    pip install grpcio grpcio-tools
    python client_test.py
"""

import subprocess
import sys
import os
import tempfile

# ============================================================================
# 1. Gera os stubs Python a partir do .proto (em diretório temporário)
# ============================================================================
PROTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "proto")
PROTO_FILE = os.path.join(PROTO_DIR, "maas.proto")
STUB_DIR = tempfile.mkdtemp(prefix="maas_stubs_")

print(f"[*] Gerando stubs Python em {STUB_DIR} ...")

result = subprocess.run(
    [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path={PROTO_DIR}",
        f"--python_out={STUB_DIR}",
        f"--grpc_python_out={STUB_DIR}",
        PROTO_FILE,
    ],
    capture_output=True,
    text=True,
)

if result.returncode != 0:
    print(f"[ERRO] protoc falhou:\n{result.stderr}", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, STUB_DIR)

import maas_pb2
import maas_pb2_grpc

import grpc

# ============================================================================
# 2. Configuração
# ============================================================================
SERVER_ADDR = os.getenv("MAAS_SERVER", "localhost:50051")
ALLOC_SIZE = 10 * 1024 * 1024  # 10 MiB
# UUID de tenant de teste — deve existir no banco.
# Para teste rápido, insira antes:
#   INSERT INTO Tenant (tenant_id, name, plan) VALUES
#     ('aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee', 'test-tenant', 'Developer');
TENANT_ID = os.getenv("MAAS_TENANT_ID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

# ============================================================================
# 3. Testa Allocate
# ============================================================================
def test_allocate(stub: maas_pb2_grpc.MemoryServiceStub) -> str:
    print(f"\n{'='*60}")
    print(f" ALLOCATE — Solicitando {ALLOC_SIZE / (1024*1024):.0f} MiB")
    print(f"{'='*60}")

    request = maas_pb2.AllocateRequest(
        tenant_id=TENANT_ID,
        size_bytes=ALLOC_SIZE,
    )

    try:
        response = stub.Allocate(request, timeout=10)
    except grpc.RpcError as e:
        print(f"[ERRO] gRPC {e.code().name}: {e.details()}", file=sys.stderr)
        sys.exit(1)

    print(f"  allocation_id : {response.allocation_id}")
    print(f"  shm_key       : {response.shm_key}")
    print(f"  offset        : {response.offset}")
    print(f"  size_bytes    : {ALLOC_SIZE} ({ALLOC_SIZE / (1024*1024):.0f} MiB)")

    return response.allocation_id

# ============================================================================
# 4. Testa Deallocate
# ============================================================================
def test_deallocate(stub: maas_pb2_grpc.MemoryServiceStub, allocation_id: str):
    print(f"\n{'='*60}")
    print(f" DEALLOCATE — Liberando {allocation_id}")
    print(f"{'='*60}")

    request = maas_pb2.DeallocateRequest(allocation_id=allocation_id)

    try:
        response = stub.Deallocate(request, timeout=10)
    except grpc.RpcError as e:
        print(f"[ERRO] gRPC {e.code().name}: {e.details()}", file=sys.stderr)
        sys.exit(1)

    print(f"  success : {response.success}")
    print(f"  message : {response.message}")

# ============================================================================
# 5. Main
# ============================================================================
def main():
    print(f"[*] Conectando a {SERVER_ADDR} ...")
    channel = grpc.insecure_channel(SERVER_ADDR)
    stub = maas_pb2_grpc.MemoryServiceStub(channel)

    # Testa Allocate
    alloc_id = test_allocate(stub)

    # Testa Deallocate
    test_deallocate(stub, alloc_id)

    channel.close()
    print(f"\n[OK] Testes concluídos com sucesso.")


if __name__ == "__main__":
    main()
