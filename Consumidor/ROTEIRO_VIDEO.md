# Roteiro do Video - Entrega 2

---

## PARTE 1 — MaaS (Memory as a Service)

### 1. Introducao ao MaaS (1min)
- Apresentar o conceito: Software-Defined Memory (SDM)
- Problema resolvido: desacoplar RAM do CPU, permitindo alocacao dinamica de memoria via rede
- Uso de memoria compartilhada POSIX (shm_open, mmap, mlock) com latencia ultra-baixa
- Comunicacao via gRPC sobre HTTP/2

### 2. Arquitetura do Servidor MaaS (1min30s)
- Servidor em C++20 (main.cpp — 762 linhas)
- ShmManager: gerenciamento do ciclo de vida dos blocos de memoria
- Operacoes principais:
  - Allocate: cria bloco de memoria compartilhada, retorna shm_key e allocation_id
  - Deallocate: libera memoria e faz cleanup
  - WriteMemory / ReadMemory: escrita e leitura remota via gRPC
  - ReportMetrics: telemetria em streaming (latencia, cache hits, pressao de memoria)
  - CheckHealth: verificacao de saude do servico
- Isolamento multi-tenant via cgroups v2
- Persistencia de metadados no PostgreSQL (libpq)

### 3. Dashboard de Observabilidade MaaS (1min)
- Dashboard Next.js 15 (React + TypeScript + TailwindCSS)
- Monitoramento em tempo real da infraestrutura:
  - KPIs de alocacoes ativas
  - Tabela de alocacoes de memoria por tenant
  - Grafico de top consumidores (Recharts)
- Gerenciamento de tenants (criar, visualizar cotas)
- Modal para novas requisicoes de alocacao de memoria
- Integracao com MaaS Core via gRPC-JS
- Auto-refresh automatico

### 4. Banco de Dados MaaS (30s)
- Schema PostgreSQL com 6 tabelas:
  - Tenant, TenantQuota, ClusterNode
  - MemoryAllocation (tabela principal de rastreamento)
  - ObservabilityMetrics (telemetria)
  - AtomicBilling (cobranca granular com hash de integridade)
- Indices otimizados para consultas por tenant e metricas

### 5. Deploy do MaaS (30s)
- Docker Compose orquestrando: PostgreSQL + MaaS Core (C++) + Dashboard (Next.js)
- Dockerfile multi-stage para o servidor C++ (build otimizado com -O2 -march=native)
- Capabilities especiais: SYS_ADMIN, IPC_LOCK para mlock
- IPC host para acesso eficiente a memoria compartilhada

---

## PARTE 2 — Sentinela Ambiental (Consumidor)

### 6. Introducao ao Sentinela (30s)
- Apresentar o projeto: monitoramento de anomalias termicas (incendios florestais e focos de calor)
- Dados: NASA FIRMS (satelite VIIRS) — cobertura global multi-regiao
- Impacto social: apoio a Defesa Civil e Corpo de Bombeiros
- Consumidor real do MaaS — utiliza memoria compartilhada para processar dados em tempo real

### 7. Pipeline de Dados — 3 Estagios (1min30s)
- **Estagio 1 — Ingestor:**
  - Busca dados termicos da API NASA FIRMS
  - Handshake gRPC com MaaS Core para alocar Buffer A (100MB)
  - Serializa registros binarios (32 bytes/registro) na memoria compartilhada
  - Cobertura multi-regiao: America do Sul, Norte, Africa, Europa, Asia, Oceania
- **Estagio 2 — Data Processor:**
  - Le registros do Buffer A via memoria compartilhada
  - Filtragem: temperatura >= 330K e confianca >= 80%
  - Extrai feature vectors (8 floats) e grava no Buffer B (50MB)
  - Persiste leituras no PostgreSQL e gera alertas
- **Estagio 3 — AI Processor:**
  - Le feature vectors do Buffer B
  - Inferencia com LightGBM (ou heuristica fallback quando modelo indisponivel)
  - Heuristica: gate de temperatura (310K), fatores de FRP, confianca e contexto temporal
  - Grava predicoes no Buffer C (20MB) e no PostgreSQL

### 8. API REST e Endpoints (30s)
- FastAPI servindo 4 endpoints:
  - GET /api/alerts — alertas termicos com deduplicacao por coordenadas
  - GET /api/stats — KPIs das ultimas 24h
  - GET /api/predictions — predicoes do modelo de IA
  - GET / — interface do globo 3D

### 9. Demonstracao do Globo 3D (2min)
- Interface interativa: Three.js + Globe.gl + TailwindCSS
- Hexagonos coloridos por severidade (CRITICAL=vermelho, INFO=azul, LOW=verde)
- Altura dos hexagonos representa FRP agregado
- Demonstrar os filtros:
  - Janela de tempo (6h, 12h, 24h, 48h, 72h)
  - Regiao (America do Sul, global, etc.)
  - Severidade (CRITICAL, INFO, LOW)
  - Tipo termal, confianca minima e FRP minimo
  - Raio do hexagono
- Tooltip com detalhes ao passar o mouse
- Auto-refresh a cada 30 segundos

### 10. KPIs e Indicadores (1min)
- Total de focos nas ultimas 24h
- Focos criticos
- Pico de FRP (Fire Radiative Power)
- Confianca media
- Exportacao de relatorio PDF com top 100 focos por FRP

### 11. Insights e Predicoes da IA (1min)
- Mostrar predicoes do modelo LightGBM
- Urgency score e classificacao de severidade
- Exemplo pratico: focos criticos detectados em uma regiao especifica
- Como esses dados auxiliam na tomada de decisao da Defesa Civil

### 12. Testes e Qualidade (30s)
- 12 modulos de teste (734 linhas)
- Cobertura: API, banco de dados, ingestor, ML, pipeline integrado, estruturas binarias
- Docker Compose orquestrando 5 servicos: db, ingestor, processor, ai_processor, dashboard

---

## Encerramento (30s)
- Resumo: MaaS como infraestrutura + Sentinela como aplicacao de ciencia de dados
- Proximos passos para a Entrega 3 (MVP final)
