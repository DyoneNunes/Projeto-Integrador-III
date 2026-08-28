# Integracoes - Sentinela Ambiental

## Google Earth Engine (GEE) - Integracao Completa

### Resumo
Integracao do Google Earth Engine para visualizacao de camadas termicas satelitais no globo 3D.
Todo processamento geoespacial ocorre nos servidores Google (doutrina MaaS). O backend local
recebe apenas URLs e escalares agregados - zero alocacao de arrays/rasters em RAM local.

---

### Arquivos Criados

#### `src/gee_service.py`
- Modulo de inicializacao do Earth Engine com Service Account
- Validacao de credenciais (`GOOGLE_APPLICATION_CREDENTIALS`)
- `initialize_gee()` - inicializa com `ee.Initialize()` usando `google.oauth2.service_account`
- `get_modis_lst_layer(days)` - gera tile_url + thumb_url para MODIS LST (1km resolucao)
  - Colecao: `MODIS/061/MOD11A1`, banda `LST_Day_1km`
  - Fallback progressivo de janela temporal: 7d → 14d → 30d → 60d
  - Fator de escala: `multiply(0.02)` para converter DN → Kelvin
  - Paleta: azul (frio) → vermelho (quente), range 250K-330K
- `get_landsat_thermal_layer(days, bbox)` - gera tile_url + thumb_url para Landsat 9 (~100m)
  - Colecao: `LANDSAT/LC09/C02/T1_L2`, banda `ST_B10`
  - Filtro: cloud_cover < 30%
  - Fator de escala: `multiply(0.00341802).add(149.0)` → Kelvin
  - Requer bbox regional (Landsat global e pesado demais para thumbnail)
  - `filterBounds()` limita espacialmente para performance
- `analyze_thermal_region(bbox, days)` - analise termica regional
  - Estatisticas via `reduceRegion()` (executado no Google, retorna ~6 escalares)
  - Baseline historica: mesmo mes, 5 anos anteriores
  - Camada de anomalia: `image_current.subtract(baseline_image)`
  - Hotspots: pixels acima de 330K contados via `reduceRegion()`
  - Retorna: tile_url_lst, tile_url_anomaly, thumb_url, thumb_url_anomaly, statistics

#### `credentials/.gitkeep`
- Diretorio para armazenar o JSON da Service Account do Google Cloud
- Arquivos `.json` dentro desta pasta sao ignorados pelo `.gitignore`

---

### Arquivos Modificados

#### `src/api.py`
- **Lifespan**: inicializa GEE no startup com graceful degradation (se falhar, endpoints retornam erro)
- **`GET /api/gee/camada-termica`** - retorna tile_url + thumb_url para MODIS ou Landsat
  - Params: `dataset` (modis|landsat), `days` (1-90), `bbox` (west,south,east,north para Landsat)
  - Executa em `asyncio.to_thread()` para nao bloquear o event loop
- **`POST /api/gee/analise/temperatura`** - analise termica regional
  - Body: `{"bbox": [west, south, east, north], "days": 7}`
  - Retorna: estatisticas agregadas + tile URLs (LST e anomalia)
  - Executa em `asyncio.to_thread()`
- **`GET /api/gee/proxy-thumb`** - proxy para thumbnails do GEE
  - Evita problemas de CORS e URLs expiradas
  - Valida que URL comeca com `https://earthengine.googleapis.com/`
  - Timeout: 90s, streaming
  - Headers: `Cache-Control: public, max-age=300`
- **`GET /api/gee/status`** - verifica se GEE esta inicializado
- Import adicionado: `asyncio`, `requests as http_requests`, `Response`, `BaseModel`

#### `static/index.html`
- **Secao "Camada Satelite (GEE)" na sidebar**:
  - Toggle para ativar/desativar camada MODIS ou Landsat
  - Seletor de dataset (MODIS LST 1km / Landsat 9 100m)
  - Slider de opacidade (10-100%)
  - Status de carregamento e legenda de cores
- **Secao "Analise Regional (GEE)" na sidebar**:
  - Seletor de modo: Temperatura LST ou Anomalia Termica
  - Botao "Analisar Regiao" que chama `POST /api/gee/analise/temperatura`
  - Painel de estatisticas: temp media/max/min, desvio padrao, anomalia media/max, hotspots
  - Legenda de anomalia termica (-10K a +10K)
- **Overlay Three.js**:
  - Esfera overlay com raio `globeRadius * 1.002` (acima do globo)
  - Textura equiretangular carregada via proxy local (`/api/gee/proxy-thumb`)
  - `MeshBasicMaterial` transparente com `depthWrite: false`
  - Rotacao `-PI/2` para alinhar com a textura do globe.gl
  - Funcao `applyGeeTexture()` reutilizada por camada e analise
  - Funcao `removeGeeOverlay()` com dispose de textura/material/geometria
- **Reatividade**:
  - Trocar regiao recarrega camada GEE automaticamente (Landsat precisa novo bbox)
  - Trocar dataset recarrega camada
  - Landsat em modo Global mostra aviso: "selecione uma regiao especifica"
- **REGION_BBOXES**: mapeamento regiao → bbox no formato GEE [west, south, east, north]

#### `.env`
```
GOOGLE_APPLICATION_CREDENTIALS=/app/credentials/gen-lang-client-0771605494-e9712fdc1fa9.json
```

#### `.env.example`
```
GOOGLE_APPLICATION_CREDENTIALS=./credentials/gee-service-account.json
```

#### `requirements.txt`
```
earthengine-api==0.1.383
google-auth==2.36.0
```

#### `Dockerfile`
- Etapa 3 de pip install adicionada:
```dockerfile
RUN pip install --no-cache-dir --timeout=120 \
    earthengine-api==0.1.383 \
    google-auth==2.36.0
```

#### `docker-compose.yml`
- Volume de credenciais adicionado ao servico dashboard:
```yaml
- ./credentials:/app/credentials:ro
```

#### `.gitignore` (raiz do projeto)
```
credentials/*.json
```

---

### Arquitetura MaaS

```
Frontend (Globe.gl / Three.js)
    |
    |-- GET /api/gee/camada-termica ──> FastAPI ──> ee.getMapId() ──> Google Cloud
    |       (retorna tile_url + thumb_url)          (processa no Google)
    |
    |-- POST /api/gee/analise/temperatura ──> FastAPI ──> ee.reduceRegion() ──> Google Cloud
    |       (retorna escalares + tile URLs)              (retorna ~6 numeros)
    |
    |-- GET /api/gee/proxy-thumb?url=... ──> FastAPI ──> requests.get(url) ──> Google Cloud
    |       (proxy PNG sem CORS)                        (streaming, sem cache local)
    |
    v
Three.js SphereGeometry overlay (textura equiretangular do thumb)
```

**Regras MaaS respeitadas:**
- `getMapId()` → retorna URL (string), zero dados
- `getThumbURL()` → retorna URL (string), zero dados
- `reduceRegion().getInfo()` → retorna dict com ~6 numeros (escalares)
- `collection.size().getInfo()` → retorna 1 inteiro
- Nenhum `.getInfo()` em imagens ou colecoes completas
- Proxy faz streaming sem armazenar em RAM

---

### Como Configurar

1. Criar projeto no Google Cloud Console
2. Ativar Earth Engine API em APIs & Services > Library
3. Criar Service Account em IAM & Admin > Service Accounts
4. Gerar chave JSON e salvar em `Consumidor/credentials/`
5. Registrar email da Service Account em signup.earthengine.google.com
6. Atualizar `GOOGLE_APPLICATION_CREDENTIALS` no `.env` com o nome do arquivo
7. `docker compose up -d --build`

---

### Refatoracao: Thumbnail Equiretangular Global (v2)

**Problema resolvido**: O thumbnail Landsat regional era mapeado na esfera inteira do globo 3D,
causando distorcao. Pixels de uma regiao (ex: America do Sul) eram esticados para cobrir o mundo todo.

**Solucao**: Todos os `getThumbURL()` agora usam `region` e `crs` explicitos:
- `region`: `ee.Geometry.Rectangle([-180, -85, 180, 85], proj='EPSG:4326', geodesic=False)`
- `crs`: `EPSG:4326`
- Resultado: imagem equiretangular global onde pixels fora da regiao Landsat ficam transparentes (PNG alpha)
- O overlay Three.js funciona sem alteracao (esfera completa + transparencia)

**Outras melhorias**:
- Cache TTL de 5 minutos para Landsat (evita re-chamadas de 10-30s ao GEE)
- Proxy timeout aumentado de 90s para 120s
- Mensagem de loading especifica para Landsat ("pode levar 15-30s")
- Legenda dinamica: atualiza range ao trocar dataset (MODIS: 250K-330K, Landsat: 270K-320K)

---

### Problemas Conhecidos

- **Landsat global**: muito pesado para gerar thumbnail (~15000 imagens em 100m). Requer selecao de regiao especifica.
- **Landsat lento**: mesmo regional, a composicao de dezenas de imagens Landsat pode demorar 10-30s no GEE. Cache TTL de 5min mitiga re-chamadas.
- **URLs temporarias**: tile_url e thumb_url do GEE expiram apos algumas horas. O frontend recarrega ao trocar regiao/dataset.
- **MODIS delay**: dados MODIS LST tem latencia de 1-2 dias. Janela temporal minima recomendada: 7 dias.
