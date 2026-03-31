#!/usr/bin/env python3
"""
MaaS — Teste de alocação via gRPC
Uso: python teste_alocacao.py

Gera os stubs automaticamente a partir do .proto.
"""

import subprocess
import sys
import os
import tempfile

# Gera stubs Python
PROTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "proto")
PROTO_FILE = os.path.join(PROTO_DIR, "maas.proto")
STUB_DIR = tempfile.mkdtemp(prefix="maas_stubs_")

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

import grpc
import maas_pb2
import maas_pb2_grpc

# ============================================================================
# Configuração — use um tenant_id UUID válido do banco de dados
# ============================================================================
TENANT_ID = os.getenv("MAAS_TENANT_ID", "1b694d7f-57a6-4596-b28d-f7451d000b4e")
SIZE_BYTES = 1 * 1024 * 1024  # 1 MB

# Conectando ao servidor MaaS
channel = grpc.insecure_channel("localhost:50051")
stub = maas_pb2_grpc.MemoryServiceStub(channel)

print(f"[*] Alocando {SIZE_BYTES} bytes para tenant {TENANT_ID}...")

try:
    response = stub.Allocate(
        maas_pb2.AllocateRequest(
            tenant_id=TENANT_ID,
            size_bytes=SIZE_BYTES,
        ),
        timeout=10,
    )
    print(f"[OK] Memória alocada!")
    print(f"  allocation_id : {response.allocation_id}")
    print(f"  shm_key       : {response.shm_key}")
    print(f"  offset        : {response.offset}")
except grpc.RpcError as e:
    print(f"[ERRO] gRPC {e.code().name}: {e.details()}", file=sys.stderr)
    sys.exit(1)
finally:
    channel.close()