#!/bin/bash
set -e

# Gera os stubs gRPC Python a partir do proto montado em /app/proto
if [ -f /app/proto/maas.proto ]; then
    echo "[*] Gerando stubs gRPC Python..."
    python -m grpc_tools.protoc \
        --proto_path=/app/proto \
        --python_out=/app/src \
        --grpc_python_out=/app/src \
        /app/proto/maas.proto
    echo "[+] Stubs gerados: src/maas_pb2.py, src/maas_pb2_grpc.py"
else
    echo "[!] AVISO: /app/proto/maas.proto não encontrado. Stubs não gerados."
fi

# Executa o comando passado (CMD do Dockerfile ou override do docker-compose)
exec "$@"
