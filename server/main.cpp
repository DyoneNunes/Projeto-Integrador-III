// =============================================================================
// PROJETO MaaS (Memory as a Service) - PI-III 5º PERÍODO TADS FAESA
// Servidor gRPC com POSIX Shared Memory (shm_open/mmap) e persistência libpq
// =============================================================================

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <mutex>
#include <optional>
#include <shared_mutex>
#include <string>
#include <unordered_map>

// Linux — POSIX shared memory + mmap
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

// gRPC / Protobuf
#include <grpcpp/grpcpp.h>
#include "maas.grpc.pb.h"

// PostgreSQL (libpq)
#include <libpq-fe.h>

// =============================================================================
// Configuração via variáveis de ambiente
// =============================================================================
struct Config {
    std::string grpc_addr   = "0.0.0.0:50051";
    std::string pg_conninfo = "host=db port=5432 dbname=postgres user=postgres password=postgres";
    std::size_t capacity    = 1ULL << 30; // 1 GiB limite lógico total
    std::size_t page_size   = 0;

    static Config from_env() {
        Config cfg;
        if (auto* v = std::getenv("MAAS_GRPC_ADDR"))   cfg.grpc_addr   = v;
        if (auto* v = std::getenv("MAAS_PG_CONNINFO"))  cfg.pg_conninfo = v;
        if (auto* v = std::getenv("MAAS_ARENA_SIZE"))   cfg.capacity    = std::stoull(v);
        cfg.page_size = static_cast<std::size_t>(sysconf(_SC_PAGESIZE));
        return cfg;
    }
};

// =============================================================================
// Utilidade: gera UUID v4 lendo do kernel Linux
// =============================================================================
static std::string generate_uuid() {
    std::ifstream ifs("/proc/sys/kernel/random/uuid");
    std::string uuid;
    if (ifs.good()) {
        std::getline(ifs, uuid);
    }
    return uuid;
}

// =============================================================================
// ShmBlock — Representa um bloco de POSIX Shared Memory mapeado
// =============================================================================
struct ShmBlock {
    std::string shm_name;     // Nome POSIX: /maas_shm_<uuid>
    int         fd;           // File descriptor do shm_open
    void*       ptr;          // Ponteiro retornado pelo mmap
    std::size_t size;         // Tamanho mapeado (alinhado a página)
    std::string allocation_id;// UUID do registro no PostgreSQL
};

// =============================================================================
// ShmManager — Gerencia o ciclo de vida de objetos POSIX Shared Memory
//
// Cada alocação cria um objeto independente em /dev/shm via shm_open(3).
// O mmap é feito com MAP_SHARED sobre o fd, e mlock trava em RAM física.
// Um contador atômico de bytes alocados impõe o limite de capacidade.
// =============================================================================
class ShmManager {
public:
    explicit ShmManager(std::size_t capacity, std::size_t page_sz)
        : capacity_(capacity), page_size_(page_sz), used_(0)
    {
        std::cout << "[SHM] Manager inicializado: capacity=" << capacity_
                  << " page_size=" << page_size_ << "\n";
    }

    ~ShmManager() {
        // Cleanup de todos os blocos ativos ao desligar o servidor
        std::unique_lock lock(mutex_);
        for (auto& [id, blk] : blocks_) {
            munlock(blk.ptr, blk.size);
            munmap(blk.ptr, blk.size);
            close(blk.fd);
            shm_unlink(blk.shm_name.c_str());
            std::cout << "[SHM] Cleanup no shutdown: " << blk.shm_name << "\n";
        }
        blocks_.clear();
    }

    ShmManager(const ShmManager&) = delete;
    ShmManager& operator=(const ShmManager&) = delete;

    struct AllocResult {
        std::string shm_name;
        void*       ptr;
        int         fd;
        std::size_t aligned_size;
    };

    // -------------------------------------------------------------------------
    // allocate — Cria um objeto POSIX SHM, trunca, mapeia e trava em RAM
    // -------------------------------------------------------------------------
    [[nodiscard]] std::optional<AllocResult> allocate(std::size_t size_bytes) {
        const std::size_t aligned = align_to_page(size_bytes);

        // Verifica capacidade lógica (atômico para fast-path sem lock)
        std::size_t current = used_.load(std::memory_order_relaxed);
        while (true) {
            if (current + aligned > capacity_) {
                std::cerr << "[SHM] Capacidade esgotada: used=" << current
                          << " requested=" << aligned
                          << " capacity=" << capacity_ << "\n";
                return std::nullopt;
            }
            if (used_.compare_exchange_weak(current, current + aligned,
                    std::memory_order_acq_rel, std::memory_order_relaxed)) {
                break;
            }
        }

        // 1. Gera nome único: /maas_shm_<uuid>
        std::string uuid = generate_uuid();
        if (uuid.empty()) {
            used_.fetch_sub(aligned, std::memory_order_relaxed);
            std::cerr << "[SHM] Falha ao gerar UUID\n";
            return std::nullopt;
        }
        std::string shm_name = "/maas_" + uuid;

        // 2. shm_open — Cria o objeto de memória compartilhada POSIX
        //    O_CREAT | O_EXCL: garante criação atômica (falha se já existe)
        //    O_RDWR: leitura e escrita
        int fd = shm_open(shm_name.c_str(), O_CREAT | O_EXCL | O_RDWR, 0666);
        if (fd == -1) {
            used_.fetch_sub(aligned, std::memory_order_relaxed);
            std::cerr << "[SHM] shm_open falhou para '" << shm_name
                      << "': " << std::strerror(errno) << "\n";
            return std::nullopt;
        }

        // 3. ftruncate — Define o tamanho do objeto SHM
        //    Sem isto o objeto tem 0 bytes e mmap falharia com SIGBUS
        if (ftruncate(fd, static_cast<off_t>(aligned)) == -1) {
            std::cerr << "[SHM] ftruncate falhou para '" << shm_name
                      << "' (" << aligned << " bytes): "
                      << std::strerror(errno) << "\n";
            close(fd);
            shm_unlink(shm_name.c_str());
            used_.fetch_sub(aligned, std::memory_order_relaxed);
            return std::nullopt;
        }

        // 4. mmap — Mapeia o objeto no espaço de endereçamento do processo
        //    MAP_SHARED: alterações são visíveis por outros processos que
        //    abrirem o mesmo objeto SHM (essencial para IPC)
        void* ptr = mmap(nullptr, aligned, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        if (ptr == MAP_FAILED) {
            std::cerr << "[SHM] mmap falhou para '" << shm_name
                      << "' (" << aligned << " bytes): "
                      << std::strerror(errno) << "\n";
            close(fd);
            shm_unlink(shm_name.c_str());
            used_.fetch_sub(aligned, std::memory_order_relaxed);
            return std::nullopt;
        }

        // 5. mlock — Trava as páginas em RAM física, impedindo swap
        //    Requer CAP_IPC_LOCK (definido no docker-compose.yml)
        if (mlock(ptr, aligned) != 0) {
            // Não é fatal: logamos warning e seguimos.
            // Em produção sem CAP_IPC_LOCK o kernel pode negar.
            std::cerr << "[SHM] mlock falhou para '" << shm_name
                      << "' (CAP_IPC_LOCK necessário): "
                      << std::strerror(errno) << "\n";
        }

        // 6. madvise HUGEPAGE — Solicita Transparent Huge Pages ao kernel
        //    Reduz TLB misses para blocos grandes (>= 2 MiB)
        if (aligned >= (2ULL << 20)) {
            madvise(ptr, aligned, MADV_HUGEPAGE);
        }

        return AllocResult{shm_name, ptr, fd, aligned};
    }

    // -------------------------------------------------------------------------
    // register_block — Registra um bloco alocado no mapa interno (pós-DB)
    // -------------------------------------------------------------------------
    void register_block(const std::string& allocation_id, ShmBlock blk) {
        std::unique_lock lock(mutex_);
        blocks_.emplace(allocation_id, std::move(blk));
    }

    // -------------------------------------------------------------------------
    // release — Desmapeia, desvincula o SHM e libera a capacidade
    // -------------------------------------------------------------------------
    bool release(const std::string& allocation_id) {
        std::unique_lock lock(mutex_);
        auto it = blocks_.find(allocation_id);
        if (it == blocks_.end()) {
            return false; // Não encontrado no mapa local
        }

        ShmBlock& blk = it->second;

        // munlock + munmap: libera o mapeamento
        munlock(blk.ptr, blk.size);
        if (munmap(blk.ptr, blk.size) == -1) {
            std::cerr << "[SHM] munmap falhou para '" << blk.shm_name
                      << "': " << std::strerror(errno) << "\n";
        }

        // close fd
        close(blk.fd);

        // shm_unlink: remove o objeto de /dev/shm
        if (shm_unlink(blk.shm_name.c_str()) == -1) {
            std::cerr << "[SHM] shm_unlink falhou para '" << blk.shm_name
                      << "': " << std::strerror(errno) << "\n";
        }

        std::size_t freed = blk.size;
        std::string name = blk.shm_name;
        blocks_.erase(it);
        lock.unlock();

        used_.fetch_sub(freed, std::memory_order_relaxed);

        std::cout << "[SHM] Liberado: " << name
                  << " (" << freed << " bytes)\n";
        return true;
    }

    // -------------------------------------------------------------------------
    // rollback — Limpa recursos SHM quando o DB insert falha (atomicidade)
    // -------------------------------------------------------------------------
    void rollback(const AllocResult& res) {
        munlock(res.ptr, res.aligned_size);
        munmap(res.ptr, res.aligned_size);
        close(res.fd);
        shm_unlink(res.shm_name.c_str());
        used_.fetch_sub(res.aligned_size, std::memory_order_relaxed);
        std::cerr << "[SHM] Rollback: " << res.shm_name << "\n";
    }

    [[nodiscard]] std::size_t used()         const { return used_.load(); }
    [[nodiscard]] std::size_t capacity()     const { return capacity_; }
    [[nodiscard]] std::size_t active_count() const {
        // Leitura eventual — não precisa de lock para métricas
        return blocks_.size();
    }

private:
    [[nodiscard]] std::size_t align_to_page(std::size_t n) const {
        return (n + page_size_ - 1) & ~(page_size_ - 1);
    }

    std::size_t                                capacity_;
    std::size_t                                page_size_;
    std::atomic<std::size_t>                   used_;
    std::unordered_map<std::string, ShmBlock>  blocks_;
    std::shared_mutex                          mutex_;
};

// =============================================================================
// DatabaseClient — Wrapper thread-safe sobre libpq
// =============================================================================
class DatabaseClient {
public:
    explicit DatabaseClient(const std::string& conninfo)
        : conninfo_(conninfo), conn_(nullptr)
    {}

    bool connect() {
        conn_ = PQconnectdb(conninfo_.c_str());
        if (PQstatus(conn_) != CONNECTION_OK) {
            std::cerr << "[DB] Conexão falhou: " << PQerrorMessage(conn_) << "\n";
            PQfinish(conn_);
            conn_ = nullptr;
            return false;
        }
        std::cout << "[DB] Conectado ao PostgreSQL\n";
        return true;
    }

    ~DatabaseClient() {
        if (conn_) PQfinish(conn_);
    }

    DatabaseClient(const DatabaseClient&) = delete;
    DatabaseClient& operator=(const DatabaseClient&) = delete;

    // -------------------------------------------------------------------------
    // insert_allocation — Insere registro na tabela MemoryAllocation
    // Parâmetros via $N para prevenir SQL injection. Retorna allocation_id.
    // -------------------------------------------------------------------------
    [[nodiscard]] std::string insert_allocation(
        const std::string& tenant_id,
        const std::string& node_id,
        const std::string& shm_key,
        int64_t offset,
        int64_t size_bytes
    ) {
        std::lock_guard lock(mutex_);
        ensure_connection();

        // Temporários nomeados — evita dangling pointers no array de params
        auto offset_s = std::to_string(offset);
        auto size_s   = std::to_string(size_bytes);

        const char* params[] = {
            tenant_id.c_str(),
            node_id.c_str(),
            shm_key.c_str(),
            offset_s.c_str(),
            size_s.c_str()
        };

        PGresult* res = PQexecParams(
            conn_,
            "INSERT INTO MemoryAllocation "
            "(tenant_id, node_id, shm_key, mmap_offset_bytes, size_bytes, state) "
            "VALUES ($1::uuid, $2::uuid, $3, $4, $5, 'active') "
            "RETURNING allocation_id::text",
            5, nullptr, params, nullptr, nullptr, 0
        );

        std::string allocation_id;
        if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0) {
            allocation_id = PQgetvalue(res, 0, 0);
        } else {
            std::cerr << "[DB] INSERT allocation falhou: " << PQerrorMessage(conn_) << "\n";
        }

        PQclear(res);
        return allocation_id;
    }

    // -------------------------------------------------------------------------
    // release_allocation — Marca alocação como 'released' e retorna metadados
    // para o ShmManager fazer o cleanup dos recursos do kernel.
    // -------------------------------------------------------------------------
    struct AllocationMeta {
        std::string shm_key;
        int64_t     size_bytes;
    };

    [[nodiscard]] std::optional<AllocationMeta> release_allocation(
        const std::string& allocation_id
    ) {
        std::lock_guard lock(mutex_);
        ensure_connection();

        const char* params[] = { allocation_id.c_str() };

        // UPDATE atômico: só altera se state='active', retorna os metadados
        PGresult* res = PQexecParams(
            conn_,
            "UPDATE MemoryAllocation "
            "SET state = 'released', released_at = CURRENT_TIMESTAMP "
            "WHERE allocation_id = $1::uuid AND state = 'active' "
            "RETURNING shm_key, size_bytes",
            1, nullptr, params, nullptr, nullptr, 0
        );

        std::optional<AllocationMeta> meta;
        if (PQresultStatus(res) == PGRES_TUPLES_OK && PQntuples(res) > 0) {
            meta = AllocationMeta{
                PQgetvalue(res, 0, 0),
                std::stoll(PQgetvalue(res, 0, 1))
            };
        } else if (PQresultStatus(res) != PGRES_TUPLES_OK) {
            std::cerr << "[DB] UPDATE release falhou: " << PQerrorMessage(conn_) << "\n";
        }
        // Se ntuples==0, alocação não encontrada ou já released — retorna nullopt

        PQclear(res);
        return meta;
    }

    // -------------------------------------------------------------------------
    // insert_metric — Insere na tabela ObservabilityMetrics
    // -------------------------------------------------------------------------
    bool insert_metric(
        const std::string& tenant_id,
        const std::string& node_id,
        const std::string& allocation_id,
        double rtt_ms,
        double cache_hit_ratio,
        double memory_pressure,
        double net_bottleneck_score
    ) {
        std::lock_guard lock(mutex_);
        ensure_connection();

        auto rtt_s   = std::to_string(rtt_ms);
        auto cache_s = std::to_string(cache_hit_ratio);
        auto mem_s   = std::to_string(memory_pressure);
        auto net_s   = std::to_string(net_bottleneck_score);

        const char* params[] = {
            tenant_id.c_str(),
            node_id.c_str(),
            allocation_id.empty() ? nullptr : allocation_id.c_str(),
            rtt_s.c_str(),
            cache_s.c_str(),
            mem_s.c_str(),
            net_s.c_str()
        };

        PGresult* res = PQexecParams(
            conn_,
            "INSERT INTO ObservabilityMetrics "
            "(tenant_id, node_id, allocation_id, rtt_ms, cache_hit_ratio, "
            " memory_pressure, net_bottleneck_score) "
            "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7)",
            7, nullptr, params, nullptr, nullptr, 0
        );

        bool ok = (PQresultStatus(res) == PGRES_COMMAND_OK);
        if (!ok) {
            std::cerr << "[DB] INSERT metric falhou: " << PQerrorMessage(conn_) << "\n";
        }
        PQclear(res);
        return ok;
    }

private:
    void ensure_connection() {
        if (!conn_ || PQstatus(conn_) != CONNECTION_OK) {
            if (conn_) PQfinish(conn_);
            conn_ = PQconnectdb(conninfo_.c_str());
            if (PQstatus(conn_) != CONNECTION_OK) {
                std::cerr << "[DB] Reconexão falhou: " << PQerrorMessage(conn_) << "\n";
            }
        }
    }

    std::string conninfo_;
    PGconn*     conn_;
    std::mutex  mutex_;
};

// =============================================================================
// MemoryServiceImpl — Implementação do serviço gRPC
// =============================================================================
class MemoryServiceImpl final : public maas::MemoryService::Service {
public:
    MemoryServiceImpl(ShmManager& shm, DatabaseClient& db, const std::string& node_id)
        : shm_(shm), db_(db), node_id_(node_id)
    {}

    // -------------------------------------------------------------------------
    // Allocate — Pipeline completo: shm_open → ftruncate → mmap → mlock → DB
    // -------------------------------------------------------------------------
    grpc::Status Allocate(
        grpc::ServerContext* /*ctx*/,
        const maas::AllocateRequest* req,
        maas::AllocateResponse* resp
    ) override {
        if (req->tenant_id().empty()) {
            return grpc::Status(grpc::INVALID_ARGUMENT, "tenant_id é obrigatório");
        }
        if (req->size_bytes() <= 0) {
            return grpc::Status(grpc::INVALID_ARGUMENT, "size_bytes deve ser > 0");
        }

        // 1. Cria o objeto POSIX SHM (shm_open + ftruncate + mmap + mlock)
        auto result = shm_.allocate(static_cast<std::size_t>(req->size_bytes()));
        if (!result) {
            return grpc::Status(grpc::RESOURCE_EXHAUSTED,
                "Falha ao alocar memória compartilhada");
        }

        // 2. Persiste metadados no PostgreSQL
        //    offset=0 porque cada alocação é um objeto SHM independente
        std::string alloc_id = db_.insert_allocation(
            req->tenant_id(),
            node_id_,
            result->shm_name,
            0,  // offset sempre 0 para POSIX SHM individual
            req->size_bytes()
        );

        if (alloc_id.empty()) {
            // Atomicidade: DB falhou → limpa recursos do kernel
            shm_.rollback(*result);
            return grpc::Status(grpc::INTERNAL, "Falha ao persistir alocação no banco");
        }

        // 3. Registra no mapa interno para lookup no Deallocate
        ShmBlock blk{
            result->shm_name,
            result->fd,
            result->ptr,
            result->aligned_size,
            alloc_id
        };
        shm_.register_block(alloc_id, std::move(blk));

        // 4. Monta resposta gRPC
        resp->set_allocation_id(alloc_id);
        resp->set_shm_key(result->shm_name);
        resp->set_offset(0);

        std::cout << "[ALLOC] tenant=" << req->tenant_id()
                  << " size=" << req->size_bytes()
                  << " shm=" << result->shm_name
                  << " id=" << alloc_id << "\n";

        return grpc::Status::OK;
    }

    // -------------------------------------------------------------------------
    // Deallocate — DB update → munmap → shm_unlink (cleanup completo)
    // -------------------------------------------------------------------------
    grpc::Status Deallocate(
        grpc::ServerContext* /*ctx*/,
        const maas::DeallocateRequest* req,
        maas::DeallocateResponse* resp
    ) override {
        if (req->allocation_id().empty()) {
            return grpc::Status(grpc::INVALID_ARGUMENT, "allocation_id é obrigatório");
        }

        // 1. Marca como 'released' no banco (atômico: só altera se state='active')
        auto meta = db_.release_allocation(req->allocation_id());
        if (!meta) {
            resp->set_success(false);
            resp->set_message("Alocação não encontrada ou já liberada");
            return grpc::Status(grpc::NOT_FOUND,
                "allocation_id não encontrado ou state != 'active'");
        }

        // 2. Libera recursos do kernel (munmap + shm_unlink)
        bool released = shm_.release(req->allocation_id());
        if (!released) {
            // Pode ocorrer se o servidor reiniciou e perdeu o mapa em memória
            // mas o registro existe no banco — cleanup manual via /dev/shm
            std::cerr << "[DEALLOC] Bloco não encontrado no mapa local: "
                      << req->allocation_id() << " (shm=" << meta->shm_key << ")\n";

            // Tenta shm_unlink direto pelo nome do banco
            shm_unlink(meta->shm_key.c_str());
        }

        resp->set_success(true);
        resp->set_message("Desalocado: " + meta->shm_key);

        std::cout << "[DEALLOC] id=" << req->allocation_id()
                  << " shm=" << meta->shm_key
                  << " size=" << meta->size_bytes << "\n";

        return grpc::Status::OK;
    }

    // -------------------------------------------------------------------------
    // ReportMetrics — Client-streaming de métricas de observabilidade
    // -------------------------------------------------------------------------
    grpc::Status ReportMetrics(
        grpc::ServerContext* /*ctx*/,
        grpc::ServerReader<maas::MetricsReport>* reader,
        maas::Acknowledge* resp
    ) override {
        maas::MetricsReport report;
        int64_t count = 0;

        while (reader->Read(&report)) {
            db_.insert_metric(
                report.tenant_id(),
                report.node_id(),
                report.allocation_id(),
                report.rtt_ms(),
                report.cache_hit_ratio(),
                report.memory_pressure(),
                report.net_bottleneck_score()
            );
            count++;
        }

        resp->set_metrics_received(count);
        resp->set_message("Recebidas " + std::to_string(count) + " métricas");

        std::cout << "[METRICS] " << count << " métricas processadas\n";
        return grpc::Status::OK;
    }

private:
    ShmManager&     shm_;
    DatabaseClient& db_;
    std::string     node_id_;
};

// =============================================================================
// Ponto de entrada
// =============================================================================
int main() {
    std::cout << "========================================\n"
              << " MaaS (Memory as a Service) - Core v0.2\n"
              << "========================================\n";

    // 1. Carrega configuração
    auto cfg = Config::from_env();
    std::cout << "[CONFIG] addr=" << cfg.grpc_addr
              << " capacity=" << cfg.capacity << "B"
              << " page=" << cfg.page_size << "B\n";

    // 2. Inicializa o gerenciador de SHM
    ShmManager shm(cfg.capacity, cfg.page_size);

    // 3. Conecta ao PostgreSQL com retry exponencial
    DatabaseClient db(cfg.pg_conninfo);
    for (int attempt = 1; attempt <= 10; ++attempt) {
        if (db.connect()) break;
        std::cerr << "[DB] Tentativa " << attempt << "/10 falhou, aguardando 2s...\n";
        sleep(2);
    }

    // 4. Identificador deste nó
    //    Stub fixo — em produção, registrar via INSERT INTO ClusterNode RETURNING node_id
    std::string node_id = "00000000-0000-0000-0000-000000000001";

    // 5. Configura e inicia o servidor gRPC
    MemoryServiceImpl service(shm, db, node_id);

    grpc::ServerBuilder builder;
    builder.AddListeningPort(cfg.grpc_addr, grpc::InsecureServerCredentials());
    builder.RegisterService(&service);

    // Tuning: limites de mensagem e threads
    builder.SetMaxReceiveMessageSize(64 * 1024 * 1024);
    builder.SetMaxSendMessageSize(64 * 1024 * 1024);

    auto server = builder.BuildAndStart();
    if (!server) {
        std::cerr << "[FATAL] Falha ao iniciar servidor gRPC\n";
        return EXIT_FAILURE;
    }

    std::cout << "[SERVER] gRPC escutando em " << cfg.grpc_addr
              << " | Capacidade: " << shm.capacity() << " bytes"
              << " | PID: " << getpid() << "\n";

    server->Wait();
    return EXIT_SUCCESS;
}
