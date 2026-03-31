#!/usr/bin/env python3
# =============================================================================
# MaaS Reader — Reads from POSIX shared memory created by the C++ backend
#
# Dependencies:
#   pip install posix_ipc grpcio grpcio-tools
# =============================================================================

import sys
import mmap

try:
    import posix_ipc
except ImportError:
    print("[ERRO] posix_ipc não encontrado. Instale com: pip install posix_ipc")
    sys.exit(1)

# ============================================================================
# Configuration
# ============================================================================
READ_SIZE = 1024  # 1 KB — must match the writer's allocation size

# ============================================================================
# Main
# ============================================================================
def main():
    # --- Step 1: Ask for the shm_key ---
    print("=" * 60)
    print("  MaaS Reader — Shared Memory Proof-of-Concept")
    print("=" * 60)
    shm_key = input("[Reader] Enter the shm_key: ").strip()

    if not shm_key:
        print("[ERRO] No shm_key provided.", file=sys.stderr)
        sys.exit(1)

    # --- Step 2: Attach to the shared memory segment ---
    print(f"[Reader] Attaching to shared memory segment '{shm_key}' ...")
    try:
        shm = posix_ipc.SharedMemory(shm_key)
    except posix_ipc.ExistentialError:
        print(f"[ERRO] Shared memory '{shm_key}' does not exist!", file=sys.stderr)
        print("       Make sure maas_writer.py is still running (waiting on ENTER).")
        sys.exit(1)

    mm = mmap.mmap(shm.fd, READ_SIZE)
    shm.close_fd()

    # --- Step 3: Read the content ---
    mm.seek(0)
    raw = mm.read(READ_SIZE)
    content = raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")

    print(f"[Reader] Read {len(content)} bytes from shared memory:")
    print(f'  "{content}"')

    # --- Step 4: Cleanup ---
    mm.close()
    print("[Reader] Done.")


if __name__ == "__main__":
    main()
