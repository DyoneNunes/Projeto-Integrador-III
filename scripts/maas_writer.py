#!/usr/bin/env python3
# =============================================================================
# MaaS Writer — Proves the C++ backend creates real POSIX shared memory
#
# Dependencies:
#   pip install posix_ipc grpcio grpcio-tools
# =============================================================================

import subprocess
import sys
import os
import tempfile
import mmap

try:
    import posix_ipc
except ImportError:
    print("[ERRO] posix_ipc não encontrado. Instale com: pip install posix_ipc")
    sys.exit(1)

# ============================================================================
# 1. Generate Python gRPC stubs from .proto
# ============================================================================
PROTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "proto")
PROTO_FILE = os.path.join(PROTO_DIR, "maas.proto")
STUB_DIR = tempfile.mkdtemp(prefix="maas_stubs_")

print("[Writer] Generating gRPC stubs ...")

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
    print(f"[ERRO] protoc failed:\n{result.stderr}", file=sys.stderr)
    sys.exit(1)

sys.path.insert(0, STUB_DIR)

import maas_pb2
import maas_pb2_grpc
import grpc

# ============================================================================
# 2. Configuration
# ============================================================================
SERVER_ADDR = os.getenv("MAAS_SERVER", "localhost:50051")
ALLOC_SIZE = 1024  # 1 KB
TENANT_ID = os.getenv("MAAS_TENANT_ID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
MESSAGE = "MaaS: High Performance Memory - Dyone & Derek"

# ============================================================================
# 3. Main
# ============================================================================
def main():
    # --- Step 1: Connect and allocate via gRPC ---
    print(f"[Writer] Connecting to MaaS server at {SERVER_ADDR} ...")
    channel = grpc.insecure_channel(SERVER_ADDR)
    stub = maas_pb2_grpc.MemoryServiceStub(channel)

    print(f"[Writer] Requesting allocation of {ALLOC_SIZE} bytes ...")
    try:
        response = stub.Allocate(
            maas_pb2.AllocateRequest(
                tenant_id=TENANT_ID,
                size_bytes=ALLOC_SIZE,
            ),
            timeout=10,
        )
    except grpc.RpcError as e:
        print(f"[ERRO] gRPC {e.code().name}: {e.details()}", file=sys.stderr)
        sys.exit(1)

    shm_key = response.shm_key
    offset = response.offset
    allocation_id = response.allocation_id

    print(f"[Writer] Allocation successful!")
    print(f"  allocation_id : {allocation_id}")
    print(f"  shm_key       : {shm_key}")
    print(f"  offset        : {offset}")

    # --- Step 2: Attach to the POSIX shared memory created by C++ ---
    print(f"\n[Writer] Attaching to shared memory segment '{shm_key}' ...")
    try:
        shm = posix_ipc.SharedMemory(shm_key)
    except posix_ipc.ExistentialError:
        print(f"[ERRO] Shared memory '{shm_key}' does not exist!", file=sys.stderr)
        sys.exit(1)

    mm = mmap.mmap(shm.fd, ALLOC_SIZE, offset=offset)
    shm.close_fd()

    # --- Step 3: Write the message into shared memory ---
    encoded = MESSAGE.encode("utf-8")
    mm.seek(0)
    mm.write(encoded)
    mm.flush()

    print(f"[Writer] Wrote {len(encoded)} bytes into shared memory:")
    print(f'  "{MESSAGE}"')

    # --- Step 4: Wait so the reader can access the memory ---
    print(f"\n{'='*60}")
    print(f"  shm_key = {shm_key}")
    print(f"{'='*60}")
    print("[Writer] Press ENTER to release the memory and exit ...")
    input()

    mm.close()
    channel.close()
    print("[Writer] Done.")


if __name__ == "__main__":
    main()
