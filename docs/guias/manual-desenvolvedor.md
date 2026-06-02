# Manual do Desenvolvedor

Guia para quem vai **estender** o MaaS ou **integrar** um novo cliente.

## Estrutura do repositório

```text
Projeto-Integrador-III/
├── server/        # MaaS Core (C++): main.cpp, CMakeLists.txt
├── dashboard/     # Painel Next.js 14 + Prisma
├── db/            # schema.sql (PostgreSQL)
├── proto/         # maas.proto (contrato gRPC — fonte da verdade)
├── scripts/       # clientes de teste em Python
├── Consumidor/    # Sentinela Ambiental (cliente Python, compose próprio)
├── docs/          # esta documentação (MkDocs)
├── Dockerfile     # build do Core
└── docker-compose.yml
```

## Fluxo de desenvolvimento

### Alterando o contrato gRPC
1. Edite [`proto/maas.proto`](../api-grpc.md).
2. **Core (C++):** o `CMake` regenera `maas.pb.*`/`maas.grpc.pb.*` no build.
3. **Dashboard:** carrega o `.proto` em runtime (`@grpc/proto-loader`) — sem geração manual.
4. **Consumidor:** o `entrypoint.sh` regenera `maas_pb2*.py` ao subir o container.

> O `.proto` é a fonte única da verdade — mantenha os três consumidores alinhados a ele.

### Compilando o Core localmente
```bash
cd server
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
./build/maas-core
```
Dependências de sistema: `cmake`, `pkg-config`, `libgrpc++-dev`, `protobuf-compiler-grpc`, `libprotobuf-dev`, `libpq-dev`.

### Mexendo no banco
Edite [`db/schema.sql`](../banco-de-dados.md) e mantenha o `dashboard/prisma/schema.prisma` em sincronia (`npx prisma generate` no Dashboard após mudanças).

### Rodando o Dashboard em modo dev
```bash
cd dashboard
npm install && npx prisma generate
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/postgres \
MAAS_CORE_HOST=localhost:50051 npm run dev
```

## Escrevendo um novo cliente

Qualquer linguagem com gRPC serve. O ciclo de vida é sempre:

```mermaid
flowchart LR
    A["Allocate<br/>(shm_key)"] --> B{Mesma máquina?}
    B -->|Sim| C["Attach local<br/>posix_ipc + mmap"]
    B -->|Não| D["WriteMemory / ReadMemory<br/>via gRPC"]
    C --> E["Deallocate"]
    D --> E
```

Boas práticas:

- **Sempre** chame `Deallocate` (idealmente em `finally`/RAII).
- Trate `RESOURCE_EXHAUSTED` (arena cheia) e `OUT_OF_RANGE` (offset inválido).
- Defina *deadlines* nas chamadas gRPC (o Dashboard usa 10s no `Allocate`).
- Para blocos grandes, lembre do limite de **64 MiB** por mensagem gRPC.

Veja exemplos prontos em `scripts/` (`maas_writer.py`, `maas_reader.py`, `client_test.py`) e a referência completa em [Contrato gRPC](../api-grpc.md).

## Considerações de produção

- **Capabilities:** o Core precisa de `IPC_LOCK` (mlock) e `SYS_ADMIN` (huge pages). Já configurados no `docker-compose.yml`.
- **`node_id`:** hoje é fixo (MVP). Em produção, registre nós reais em `ClusterNode` e devolva o `node_id` correspondente.
- **Não implementado ainda:** isolamento por `cgroups` e deduplicação *copy-on-write* no Core (campos reservados no schema).
- **Volatilidade:** os dados vivem só na RAM; o banco guarda apenas metadados.
