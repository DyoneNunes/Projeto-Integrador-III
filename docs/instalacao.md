# Instalação e Execução

## Pré-requisitos

- **Docker** e **Docker Compose**
- Kernel **Linux** — o Core depende de `shm_open`, `mmap`, `mlock` e `madvise`

## Subir a stack do MaaS

A partir da raiz do repositório:

```bash
docker compose up -d --build
```

Sobem três serviços:

| Serviço | Acesso | Descrição |
| :--- | :--- | :--- |
| **Dashboard** | <http://localhost:3002> | Painel PaaS (Next.js) |
| **MaaS Core** | `localhost:50051` (gRPC) | Servidor C++ |
| **PostgreSQL** | `localhost:5433` | Banco do MaaS (schema auto-inicializado) |

!!! note "Capabilities do Core"
    No `docker-compose.yml`, o serviço `maas-core` recebe `cap_add: SYS_ADMIN` (para `madvise(MADV_HUGEPAGE)`) e `IPC_LOCK` (para `mlock`), além de `ipc: host` e `ulimits.memlock` ilimitado. Sem isso, `mlock`/huge pages podem falhar (de forma não-fatal).

### Verificar saúde

```bash
docker compose ps
docker compose logs -f maas-core
```

O Core expõe a RPC `CheckHealth` (retorna `SERVING`). Use as coleções
`postman_maas_grpc.json` / `insomnia_maas_grpc.json` na raiz, ou os scripts em `scripts/`.

## Subir o Sentinela Ambiental (cliente de demonstração)

O Consumidor tem seu **próprio** compose:

```bash
cd Consumidor
cp .env.example .env   # preencha NASA_MAP_KEY, conexões e credenciais GEE
docker compose up -d --build
```

| Serviço | Acesso |
| :--- | :--- |
| **Sentinela Dashboard (3D)** | <http://localhost:8000> |
| **PostgreSQL (insights)** | `localhost:5436` |

!!! warning "Rede Docker compartilhada"
    Ambas as stacks usam a rede `maas-network`. A stack do MaaS a cria; se subir o Consumidor isoladamente, garanta que ela exista (ou declare-a como `external: true`).

## Variáveis de ambiente

### MaaS Core
| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `MAAS_GRPC_ADDR` | `0.0.0.0:50051` | Endereço de escuta gRPC |
| `MAAS_PG_CONNINFO` | `host=db port=5432 dbname=postgres user=postgres password=postgres` | Conexão libpq |
| `MAAS_ARENA_SIZE` | `1073741824` (1 GiB) | Teto lógico de memória alocável |

### Dashboard
| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `DATABASE_URL` | — | Conexão PostgreSQL (Prisma) |
| `MAAS_CORE_HOST` | `maas-core:50051` | Endpoint gRPC do Core |
| `PROTO_PATH` | `./proto/maas.proto` | Caminho do contrato gRPC |

## Desenvolvimento local (sem Docker)

### Core (C++)
```bash
cd server
cmake -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
./build/maas-core
```
Dependências: `cmake`, `libgrpc++-dev`, `protobuf-compiler-grpc`, `libprotobuf-dev`, `libpq-dev`.

### Dashboard (Next.js)
```bash
cd dashboard
npm install
npx prisma generate
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/postgres \
MAAS_CORE_HOST=localhost:50051 \
npm run dev      # http://localhost:3000
```

## Rodar a documentação (MkDocs)

```bash
pip install mkdocs-material
mkdocs serve     # http://127.0.0.1:8000
mkdocs build     # site estático em ./site
```
