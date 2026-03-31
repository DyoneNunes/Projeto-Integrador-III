# =============================================================================
# PROJETO MaaS (Memory as a Service) - Multi-stage build C++20
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build — Compilação do servidor gRPC C++20
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    pkg-config \
    libgrpc++-dev \
    protobuf-compiler-grpc \
    libprotobuf-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copia proto e server separadamente para cache de camadas
COPY proto/ ./proto/
COPY server/ ./server/

# Compila com CMake
WORKDIR /build/server
RUN cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CXX_FLAGS="-O2 -DNDEBUG" \
    && cmake --build build --parallel "$(nproc)"

# Coleta apenas as shared libs necessárias pelo binário (via ldd)
RUN mkdir -p /runtime-libs && \
    ldd build/maas-core | grep '=> /' | awk '{print $3}' | \
    xargs -I{} cp -vL {} /runtime-libs/

# ---------------------------------------------------------------------------
# Stage 2: Runtime — Imagem mínima para execução
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS runtime

# Copia as shared libs identificadas via ldd do builder
COPY --from=builder /runtime-libs/ /usr/lib/
RUN ldconfig

# Cria usuário não-root para o serviço
RUN useradd --system --no-create-home maas

WORKDIR /app

# Copia o binário compilado
COPY --from=builder /build/server/build/maas-core .

# Porta gRPC
EXPOSE 50051

# Capabilities necessárias são adicionadas via docker-compose (SYS_ADMIN, IPC_LOCK)
USER maas

ENTRYPOINT ["./maas-core"]
