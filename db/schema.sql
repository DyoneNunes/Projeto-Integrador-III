-- =============================================================================
-- PROJETO MaaS (Memory as a Service) - PI-III 5º PERÍODO TADS FAESA
-- DESENVOLVEDORES: Dyone Andrade
-- ORIENTADOR: Mestre Howard Roatti
-- =============================================================================

-- Habilita a extensão para geração de UUIDs (Identificadores Únicos Universais)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- -----------------------------------------------------------------------------
-- DEFINIÇÃO DE TIPOS ENUMERADOS (DOMÍNIOS DE STATUS)
-- -----------------------------------------------------------------------------
CREATE TYPE tenant_status AS ENUM ('active', 'suspended', 'closed');
CREATE TYPE node_status AS ENUM ('healthy', 'degraded', 'offline', 'maintenance');
CREATE TYPE allocation_state AS ENUM ('provisioning', 'active', 'releasing', 'released', 'failed');

-- -----------------------------------------------------------------------------
-- TABELA: Tenant (Clientes do PaaS)
-- -----------------------------------------------------------------------------
CREATE TABLE Tenant (
    tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    plan TEXT NOT NULL, -- Ex: 'Free', 'Developer', 'Enterprise'
    status tenant_status DEFAULT 'active',
    api_key TEXT UNIQUE,  -- Chave de autenticação do tenant (maas_live_...)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------------
-- TABELA: TenantQuota (Limites de recursos por Cliente)
-- -----------------------------------------------------------------------------
CREATE TABLE TenantQuota (
    quota_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES Tenant(tenant_id) ON DELETE CASCADE,
    ram_bytes_limit BIGINT NOT NULL CHECK (ram_bytes_limit >= 0),
    max_allocations INT NOT NULL CHECK (max_allocations >= 0),
    max_nodes INT NOT NULL CHECK (max_nodes >= 0),
    effective_from TIMESTAMP WITH TIME ZONE NOT NULL,
    effective_to TIMESTAMP WITH TIME ZONE,
    CONSTRAINT unique_tenant_period UNIQUE (tenant_id, effective_from)
);

-- -----------------------------------------------------------------------------
-- TABELA: ClusterNode (Servidores Físicos/VPS que provêem a RAM)
-- -----------------------------------------------------------------------------
CREATE TABLE ClusterNode (
    node_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hostname TEXT UNIQUE NOT NULL, -- Nome do servidor na rede
    region TEXT NOT NULL,          -- Ex: 'sa-east-1' (Vitória)
    total_ram_bytes BIGINT NOT NULL,
    allocatable_ram_bytes BIGINT NOT NULL,
    status node_status DEFAULT 'healthy',
    last_heartbeat_at TIMESTAMP WITH TIME ZONE
);

-- -----------------------------------------------------------------------------
-- TABELA: MemoryAllocation (O "Coração" do projeto - Registro do mmap)
-- -----------------------------------------------------------------------------
CREATE TABLE MemoryAllocation (
    allocation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES Tenant(tenant_id),
    node_id UUID NOT NULL REFERENCES ClusterNode(node_id),
    shm_key TEXT NOT NULL,              -- Chave de Shared Memory do Linux
    mmap_offset_bytes BIGINT NOT NULL CHECK (mmap_offset_bytes >= 0),
    size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
    isolation_cgroup_path TEXT,         -- Caminho do isolamento no Kernel
    state allocation_state DEFAULT 'provisioning',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    released_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT check_offsets CHECK (size_bytes > 0 AND mmap_offset_bytes >= 0)
);

-- -----------------------------------------------------------------------------
-- TABELA: ObservabilityMetrics (Dados de telemetria em tempo real)
-- -----------------------------------------------------------------------------
CREATE TABLE ObservabilityMetrics (
    metric_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES Tenant(tenant_id),
    node_id UUID REFERENCES ClusterNode(node_id),
    allocation_id UUID REFERENCES MemoryAllocation(allocation_id) ON DELETE SET NULL,
    ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    rtt_ms NUMERIC,                     -- Round Trip Time (Latência de rede)
    cache_hit_ratio NUMERIC CHECK (cache_hit_ratio >= 0 AND cache_hit_ratio <= 1),
    memory_pressure NUMERIC,            -- Pressão sobre a RAM do Node
    net_bottleneck_score NUMERIC,       -- Score de gargalo de rede
    stress_score NUMERIC                -- Nível de estresse do sistema
);

-- -----------------------------------------------------------------------------
-- TABELA: AtomicBilling (Faturamento granulado por consumo)
-- -----------------------------------------------------------------------------
CREATE TABLE AtomicBilling (
    billing_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES Tenant(tenant_id),
    allocation_id UUID REFERENCES MemoryAllocation(allocation_id),
    metric_id UUID REFERENCES ObservabilityMetrics(metric_id),
    ts_start TIMESTAMP WITH TIME ZONE NOT NULL,
    ts_end TIMESTAMP WITH TIME ZONE NOT NULL,
    bytes_per_second BIGINT NOT NULL,
    billed_bytes BIGINT NOT NULL,
    unit_price_micros BIGINT NOT NULL,  -- Preço micro-precificado (evita floats)
    amount_micros BIGINT NOT NULL,      -- Total a cobrar em micros
    integrity_hash TEXT,                -- Hash para auditoria de cobrança
    CONSTRAINT check_dates CHECK (ts_end > ts_start),
    CONSTRAINT check_values CHECK (bytes_per_second >= 0 AND amount_micros >= 0)
);

-- -----------------------------------------------------------------------------
-- ÍNDICES DE PERFORMANCE (Fundamental para o 5º Período)
-- -----------------------------------------------------------------------------
CREATE INDEX idx_metrics_tenant_ts ON ObservabilityMetrics(tenant_id, ts DESC);
CREATE INDEX idx_alloc_tenant_active ON MemoryAllocation(tenant_id) WHERE state = 'active';
CREATE INDEX idx_billing_integrity ON AtomicBilling(integrity_hash);

-- -----------------------------------------------------------------------------
-- SEED: Nó padrão de desenvolvimento (obrigatório para o C++ server)
-- O main.cpp usa este node_id fixo para INSERT INTO MemoryAllocation
-- -----------------------------------------------------------------------------
INSERT INTO ClusterNode (node_id, hostname, region, total_ram_bytes, allocatable_ram_bytes, status)
VALUES ('00000000-0000-0000-0000-000000000001', 'maas-core-dev', 'local', 134217728, 134217728, 'healthy')
ON CONFLICT (node_id) DO NOTHING;

-- Comentário final para o Postgres
COMMENT ON DATABASE postgres IS 'Database for MaaS (Memory as a Service) PaaS Infrastructure';