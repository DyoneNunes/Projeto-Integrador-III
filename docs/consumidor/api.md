# API e Interface 3D

O serviço web do Sentinela é uma aplicação **FastAPI** (`src/api.py`) servida por **uvicorn** na porta **8000**. Ela expõe endpoints REST sobre o banco de insights e serve uma interface 3D interativa.

## Endpoints REST

| Endpoint | Método | Descrição |
| :--- | :--- | :--- |
| `/api/alerts?hours=24` | `GET` | Alertas recentes (join `sensor_readings` + `alerts_history`), deduplicados por coordenada; até 5000 registros |
| `/api/stats` | `GET` | KPIs das últimas 24h (total, críticos, FRP máx, confiança média) |
| `/api/predictions?hours=24` | `GET` | Predições do modelo (join com `sensor_readings`), foco em `prediction_class=1` |
| `/` | `GET` | Serve a interface 3D (`static/index.html`) |

### Endpoints Google Earth Engine

| Endpoint | Descrição |
| :--- | :--- |
| `GET /api/gee/camada-termica?dataset=modis\|landsat&days=7&bbox=...` | URLs de *tiles*/thumbnail de camada térmica |
| `POST /api/gee/analise/temperatura` | Estatísticas regionais (LST e anomalia vs. baseline histórica) |
| `GET /api/gee/proxy-thumb?url=...` | Proxy *streaming* de thumbnails (cache TTL 5 min) |
| `GET /api/gee/status` | Healthcheck da integração GEE |

!!! note "Doutrina MaaS no GEE"
    A integração com o Google Earth Engine respeita a filosofia *stateless*: as chamadas retornam **escalares** ou **URLs** (`getMapId`, `getThumbURL`, `reduceRegion().getInfo()`), nunca grandes arrays de pixels para a RAM local. O processamento pesado roda nos servidores do Google.

A inicialização do GEE é tolerante a falhas (*graceful degradation*): se as credenciais não estiverem disponíveis, os endpoints GEE retornam erro controlado e o resto da aplicação segue funcionando.

## Interface 3D

`static/index.html` é um globo interativo construído com **Three.js** + **Globe.gl** e estilizado com Tailwind:

- **Hexbins** coloridos por severidade (🔴 CRITICAL, 🔵 INFO, 🟢 LOW), com altura proporcional ao FRP agregado.
- **Filtros:** janela temporal, região, severidade, tipo térmico, confiança/FRP mínimos, raio do hexágono.
- **Camadas GEE:** alternância MODIS LST (1 km) / Landsat 9 (~100 m) com controle de opacidade.
- **Análise regional:** temperatura média/máx/mín e anomalia térmica para a região selecionada.
- **KPIs** e **tooltip** dinâmico ao passar o mouse sobre cada foco.
- **Exportação em PDF** dos principais focos (via `jsPDF`).

Auto-atualização periódica consumindo `/api/alerts`, `/api/stats` e `/api/predictions`.

## Como ele consome o MaaS

O cliente gRPC do Sentinela está em `src/maas_client.py` (classe `MaaSMemory`), que abstrai a memória remota com uma interface tipo `mmap`:

```python
mem = MaaSMemory(stub, allocation_id, size)
mem.seek(offset)          # valida limites
mem.write(packed_bytes)   # WriteMemory via gRPC
data = mem.read(n_bytes)  # ReadMemory via gRPC
```

Os estágios do [pipeline](pipeline.md) usam essa abstração (ou o attach local via `posix_ipc`) para escrever/ler os buffers A, B e C.
