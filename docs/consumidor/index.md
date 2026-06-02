# Sentinela Ambiental (Consumidor)

O **Sentinela Ambiental** (pasta `Consumidor/`) é o **cliente de demonstração** do MaaS: uma aplicação Python de *data science* que monitora anomalias térmicas (focos de calor / incêndios) a partir de dados de satélite, usando a RAM alugada do Core como meio de comunicação entre seus estágios.

!!! abstract "Por que ele importa para o projeto"
    O Sentinela prova o conceito de **Memory Disaggregation** na prática: ele é **stateless** e move o volume de dados para a memória compartilhada gerenciada pelo MaaS, em vez de manter tudo em arrays locais no próprio processo.

## Stack

**Python 3.11**. Principais bibliotecas (`Consumidor/requirements.txt`):

| Biblioteca | Papel |
| :--- | :--- |
| `grpcio` / `grpcio-tools` | Cliente gRPC e geração de stubs do `maas.proto` |
| `posix_ipc` | Acesso a shared memory POSIX (attach local) |
| `psycopg2-binary` | PostgreSQL (banco de insights) |
| `fastapi` + `uvicorn` | API REST e serviço web (porta 8000) |
| `numpy`, `scikit-learn`, `lightgbm` | Pré-processamento e modelo de IA |
| `earthengine-api`, `google-auth` | Integração Google Earth Engine |
| `requests` | NASA FIRMS, proxy de tiles GEE |

## Componentes da stack (`Consumidor/docker-compose.yml`)

| Serviço | Comando | Porta |
| :--- | :--- | :--- |
| `db` (`sentinela_db`) | PostgreSQL 15-alpine | `5436` |
| `ingestor` | `python src/ingestor.py` | — |
| `processor` | `python src/data_processor.py` | — |
| `ai_processor` | `python src/ai_processor.py` | — |
| `dashboard` | `uvicorn src.api:app` | `8000` |

O `entrypoint.sh` gera os stubs gRPC (`maas_pb2*.py`) a partir de `/app/proto/maas.proto` antes de iniciar cada serviço.

## Banco próprio

O Sentinela mantém um schema **separado** (`sentinela_ambiental`) com:

- `sensor_readings` — leituras brutas (deduplicadas por coordenada/temperatura arredondadas).
- `alerts_history` — alertas categorizados (`THERMAL_ANOMALY` / `AMBIENT_READING`; severidade `CRITICAL` / `INFO` / `LOW`).
- `ai_predictions` — saída do modelo (classe, probabilidade, urgência).
- *Views* analíticas (`vw_foci_by_region`, `vw_frp_intensity_trend`, `vw_bias_monitor`).

## Configuração (`.env`)

| Variável | Descrição |
| :--- | :--- |
| `NASA_MAP_KEY` | Chave da API NASA FIRMS (VIIRS/MODIS) |
| `MAAS_GRPC_HOST` | Endereço do MaaS Core (ex.: `host:50051`) |
| `MAAS_BUFFER_SIZE` / `_B_SIZE` / `_C_SIZE` | Tamanhos dos 3 buffers |
| `DB_CONNECTION` | PostgreSQL de insights (Sentinela) |
| `MAAS_DB_URL` | Banco de alocações do MaaS Core |
| `GOOGLE_APPLICATION_CREDENTIALS` | JSON da Service Account do GEE |
| `MODEL_PATH` / `MODEL_VERSION` | Modelo LightGBM treinado |
| `TENANT_NAME` | Identificação do tenant no MaaS |

Continue em [Pipeline de Dados](pipeline.md) e [API e Interface 3D](api.md).
