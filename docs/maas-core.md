# MaaS Core (C++)

O **MaaS Core** (`server/main.cpp`) é o coração do sistema: um servidor **gRPC síncrono** em **C++20** que aloca e gerencia memória física via POSIX shared memory, persistindo metadados no PostgreSQL.

## Inicialização

```
main()
 ├─ Config::from_env()              # lê variáveis de ambiente
 ├─ ShmManager(capacity, page_size) # gerenciador de shared memory
 ├─ DatabaseClient(conninfo)        # conecta no Postgres (retry com backoff)
 ├─ MemoryServiceImpl(shm, db, node_id)
 └─ ServerBuilder → AddListeningPort(:50051) → server->Wait()
```

- Limites de mensagem gRPC: **64 MiB** para envio e recepção (permite I/O de blocos grandes).
- `node_id` é fixo no MVP: `00000000-0000-0000-0000-000000000001` (semeado no `schema.sql`).

## Gerenciamento de memória

Cada `Allocate` cria um **objeto POSIX shared memory independente** (não há arena com sub-offsets). O fluxo do `ShmManager::allocate`:

```cpp
// 1. Alinha o tamanho à página (sysconf(_SC_PAGESIZE))
aligned = (n + page_size - 1) & ~(page_size - 1);

// 2. Reserva capacidade de forma lock-free (fast path)
//    used_ é std::atomic<size_t>; CAS com memory_order_acq_rel
if (current + aligned > capacity_) return nullopt;   // RESOURCE_EXHAUSTED

// 3. Cria o objeto SHM atomicamente
shm_name = "/maas_" + uuid;
fd = shm_open(shm_name, O_CREAT | O_EXCL | O_RDWR, 0666);

// 4. Dimensiona (sem isto, mmap causaria SIGBUS)
ftruncate(fd, aligned);

// 5. Mapeia
ptr = mmap(nullptr, aligned, PROT_READ|PROT_WRITE, MAP_SHARED, fd, 0);

// 6. Trava em RAM (sem swap) — requer CAP_IPC_LOCK
mlock(ptr, aligned);

// 7. Huge pages para blocos >= 2 MiB — requer CAP_SYS_ADMIN
madvise(ptr, aligned, MADV_HUGEPAGE);
```

A **liberação** (`release`) desfaz tudo na ordem inversa: `munlock` → `munmap` → `close(fd)` → `shm_unlink` (remove de `/dev/shm`) e decrementa o contador atômico.

!!! note "Capacidade lógica"
    O contador `used_` impõe o teto `MAAS_ARENA_SIZE`. Ele é puramente lógico: a memória física só é efetivamente comprometida pelo kernel conforme as páginas são tocadas (e travadas por `mlock`).

!!! warning "Não implementado neste estágio"
    **`cgroups`** (campo `isolation_cgroup_path` existe no schema mas não é usado pelo Core) e **deduplicação copy-on-write**. A deduplicação de dados acontece na camada do cliente (Sentinela), por arredondamento de coordenadas.

## Concorrência e thread-safety

| Estrutura | Mecanismo | Uso |
| :--- | :--- | :--- |
| `used_` (capacidade) | `std::atomic` + CAS | Reserva lock-free no fast path |
| `blocks_` (mapa de alocações) | `std::shared_mutex` | Múltiplos leitores (read/write/has), escritor exclusivo (register/release) |
| Conexão libpq | `std::mutex` | Serializa operações no banco (libpq não é thread-safe por conexão) |

As RPCs do `MemoryServiceImpl` rodam em paralelo no thread pool do gRPC; a sincronização é delegada ao `ShmManager` e ao `DatabaseClient`.

## Persistência (libpq)

O `DatabaseClient` usa **libpq** diretamente:

| Operação | SQL | Tabela |
| :--- | :--- | :--- |
| `insert_allocation` | `INSERT ... RETURNING allocation_id` | `MemoryAllocation` |
| `release_allocation` | `UPDATE ... SET state='released', released_at=NOW() WHERE ... AND state='active' RETURNING shm_key, size_bytes` | `MemoryAllocation` |
| `insert_metric` | `INSERT INTO ObservabilityMetrics (...)` | `ObservabilityMetrics` |

O `UPDATE` condicional em `Deallocate` garante **atomicidade** (evita double-free). Há `ensure_connection()` para reconexão automática.

## Variáveis de ambiente

| Variável | Padrão | Descrição |
| :--- | :--- | :--- |
| `MAAS_GRPC_ADDR` | `0.0.0.0:50051` | Endereço de escuta gRPC |
| `MAAS_PG_CONNINFO` | `host=db port=5432 dbname=postgres user=postgres password=postgres` | Conexão libpq |
| `MAAS_ARENA_SIZE` | `1073741824` (1 GiB) | Teto lógico de memória |

## Build

### CMake (`server/CMakeLists.txt`)
- C++20, flags `-Wall -Wextra -Wpedantic -O2 -march=native`.
- Dependências: `Threads`, `Protobuf`, `grpc++`, `libpq`; linka `rt` (POSIX shm).
- Gera os stubs do `proto/maas.proto` (`maas.pb.*` e `maas.grpc.pb.*`) via `protoc` + `grpc_cpp_plugin` em um passo customizado.

### Dockerfile (multi-stage)
1. **builder** (`debian:bookworm-slim`): instala toolchain, compila e coleta as libs dinâmicas via `ldd`.
2. **runtime** (`debian:bookworm-slim`): copia apenas o binário e as libs necessárias, roda como usuário não-root `maas`.

Veja o [Contrato gRPC](api-grpc.md) para a especificação das RPCs implementadas.
