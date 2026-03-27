# MaaS: Memory as a Service (PaaS) 🚀

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![C++](https://img.shields.io/badge/C++-20-00599C?logo=cplusplus)
![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)
![gRPC](https://img.shields.io/badge/gRPC-High%20Performance-4285F4?logo=grpc)
![Docker](https://img.shields.io/badge/Docker-Infrastructure-2496ED?logo=docker)

**MaaS (Memory as a Service)** é uma infraestrutura de **Software-Defined Memory (SDM)** desenvolvida como uma plataforma de serviços (PaaS). O projeto visa desatrelar a memória volátil (RAM) da CPU física, permitindo a alocação dinâmica de pools de memória via rede com latência ultra-baixa.

---

## 📌 Contexto Acadêmico
Este projeto é desenvolvido como parte integrante da Unidade Curricular **Projeto Integrador Computação III** (5º Período) do curso de Tecnologia em Análise e Desenvolvimento de Sistemas (**TADS**) na **FAESA Centro Universitário**.

**Orientador:** Mestre Howard Roatti

---

## 🛠️ Tecnologias e Arquitetura

O ecossistema MaaS é dividido em dois planos principais para garantir performance e escalabilidade:

### Data Plane (Motor de Performance)
* **Linguagem:** C++20 (Foco em gerenciamento manual de memória e ausência de Garbage Collector).
* **Alocação:** Utilização de `mmap`, `shm` e `cgroups v2` para isolamento de tenants no Kernel Linux.
* **Comunicação:** Protocolo gRPC sobre HTTP/2 com Protocol Buffers para serialização binária.
* **Tiering:** Algoritmo LRU customizado para swap inteligente entre RAM e NVMe.

### Control Plane (Gestão e PaaS)
* **Dashboard:** Next.js 15 (React) para interface administrativa e métricas.
* **Backend de Gestão:** API em Node.js integrada ao motor C++.
* **Persistência:** PostgreSQL (Dados relacionais) e Redis (Telemetria em tempo real).
* **Observabilidade:** Stack Prometheus & Grafana para monitoramento de latência e IOPS.

---

## 👥 Colaboradores (Core Team)

* **Dyone Andrade** - *Full Stack Developer, DevOps Engineer & Engineer IA* * **Derek Cobain** - *Software Engineer*

---

## 📂 Estrutura do Projeto (MVP C1)

```bash
├── maas-core/         # Motor de memória em C++
├── maas-dashboard/    # Interface PaaS em Next.js
├── maas-sdk/          # Biblioteca de integração para clientes
├── infra/             # Dockerfiles e Scripts de CI/CD (GitHub Actions)
└── docs/              # Documentação técnica e Diagramas (LaTeX)
# Projeto-Integrador-III
