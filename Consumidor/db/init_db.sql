-- Extensão para UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Dar permissões para que serviços externos na rede possam criar tabelas (Necessário para MaaS Core)
ALTER ROLE postgres SUPERUSER;
GRANT ALL ON SCHEMA public TO postgres;

-- Tabela de Tenants
CREATE TABLE IF NOT EXISTS public.tenant (
    tenant_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    plan VARCHAR(50) DEFAULT 'Developer',
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de Alocações (Infraestrutura MaaS) - Versão Estendida para Persistência
CREATE TABLE IF NOT EXISTS public.allocation (
    allocation_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES public.tenant(tenant_id),
    shm_key VARCHAR(255) NOT NULL,
    size_bytes BIGINT NOT NULL,
    offset_bytes BIGINT DEFAULT 0,
    status VARCHAR(50) DEFAULT 'active',
    heartbeat TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Campo exigido pelo MaaS Core
    expiry TIMESTAMP DEFAULT (CURRENT_TIMESTAMP + INTERVAL '24 hours'), -- Campo exigido pelo MaaS Core
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Schema da Aplicação "Sentinela Ambiental"
CREATE SCHEMA IF NOT EXISTS sentinela_ambiental;

-- Tabelas da Aplicação
CREATE TABLE IF NOT EXISTS sentinela_ambiental.sensors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    type VARCHAR(50) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO sentinela_ambiental.sensors (name, type, description) 
VALUES ('NASA_FIRMS_VIIRS', 'SATELLITE', 'VIIRS 375m / MODIS NRT') 
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS sentinela_ambiental.sensor_readings (
    id SERIAL PRIMARY KEY,
    sensor_id INT REFERENCES sentinela_ambiental.sensors(id),
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    temperature_k DOUBLE PRECISION NOT NULL,
    confidence INT,
    reading_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sentinela_ambiental.alerts_history (
    id SERIAL PRIMARY KEY,
    reading_id INT REFERENCES sentinela_ambiental.sensor_readings(id),
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    description TEXT,
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
