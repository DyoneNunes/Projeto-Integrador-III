# Dashboard (Next.js)

O painel PaaS em `dashboard/` é uma aplicação **Next.js 14** (App Router, Server Components) que orquestra alocações e oferece observabilidade.

## Stack

| Dependência | Versão | Papel |
| :--- | :--- | :--- |
| `next` | 14.2.x | Framework (App Router, SSR) |
| `react` / `react-dom` | 18.3.x | UI |
| `@prisma/client` + `@prisma/adapter-pg` | 7.6.x | ORM + adapter PostgreSQL |
| `@grpc/grpc-js` + `@grpc/proto-loader` | — | Cliente gRPC do Core |
| `recharts` | 3.x | Gráficos |
| `jspdf` + `jspdf-autotable` | 4.x / 5.x | Exportação de relatórios em PDF |
| `tailwindcss` | 3.4.x | Estilo (tema escuro) |

`next.config.js` usa `output: "standalone"` e marca `@grpc/*` como pacotes externos de Server Components.

## Páginas

### Home (`/`)
Renderização dinâmica (`force-dynamic`, `revalidate: 0`) com auto-refresh a cada 5s. Mostra:

- **Cards de KPI:** RAM total ativa, tenants ativos, saúde do banco.
- **Top Tenants por memória ativa** (gráfico de barras, Recharts).
- **Tabela das últimas 50 alocações** (id, tenant, tamanho, shm_key, estado, data).
- **Ações no header:** `Tenants`, `Relatório`, `Allocate Memory`.

### Tenants (`/tenants`)
Criação de tenant (formulário) e listagem com plano, `api_key` mascarada (copiável), nº de alocações ativas e status.

## API Routes

| Rota | Método | Função |
| :--- | :--- | :--- |
| `/api/tenants` | `GET` | Lista tenants + contagem de alocações ativas |
| `/api/tenants` | `POST` | Cria tenant e gera `api_key` (`maas_live_...`) |
| `/api/allocate` | `POST` | Valida tenant, chama gRPC `Allocate`, confirma persistência |
| `/api/report` | `GET` | Agrega consumo por período |

### `POST /api/allocate`
```jsonc
// request
{ "tenant_id": "uuid", "size_mb": 256 }   // size_mb: 1..512
// response
{ "allocation_id": "...", "shm_key": "/maas_...", "offset": "0",
  "size_bytes": 268435456, "tenant_name": "lab-01",
  "db_confirmed": true, "db_state": "active" }
```
Internamente chama `allocateMemory()` em `src/lib/gRPC_Client`, que carrega o `proto/maas.proto` e conecta em `MAAS_CORE_HOST` (timeout de 10s).

## Funcionalidades

### Criar tenant
Formulário → `POST /api/tenants` → exibe a `api_key` gerada (copiável) → atualiza a lista.

### Alocar memória
Modal com seletor de tenant e *slider* de 1–512 MB → `POST /api/allocate` → gRPC `Allocate` no Core → *toast* com `shm_key` e atualização da tabela.

### Relatório de consumo mensal
Modal acionado pelo botão **Relatório**:

- **Período** (datas De/Até) com atalhos ("Este mês", "Últimos 3/6 meses").
- **Resumo:** total alocado e nº de alocações no período.
- **Gráfico** de evolução mês a mês (Recharts).
- **Tabela** de consumo por tenant.
- **Exportação:**
    - **CSV** — resumo + por tenant + por mês.
    - **PDF** (`jspdf` + `jspdf-autotable`) — cabeçalho com período, tabela por tenant, evolução mensal e **lista detalhada de alocações**.

O backend (`GET /api/report?from=&to=`) roda em paralelo: `groupBy` por tenant, `aggregate` de totais, `date_trunc('month')` para a série mensal e `findMany` da lista detalhada (até 1000 itens).

## Build & deploy

`Dockerfile` multi-stage (Node 20 Alpine): instala deps → `npx prisma generate` → `npm run build` → imagem final *standalone* rodando como usuário não-root (`node server.js`, porta 3000, exposta como `3002`).

Variáveis: `DATABASE_URL`, `MAAS_CORE_HOST`, `PROTO_PATH` (opcional).
