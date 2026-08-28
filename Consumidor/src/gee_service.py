"""
Sentinela Ambiental - Google Earth Engine Service
Inicializa o GEE com Service Account e gera tile URLs para camadas termicas.

DOUTRINA MaaS: Todo processamento geoespacial ocorre nos servidores Google.
O backend local recebe apenas URLs (strings) e escalares agregados (numeros).
Nenhuma matriz, raster ou array e alocado em RAM local.
"""
import os
import time
import ee
from google.oauth2 import service_account as sa
from datetime import datetime, timedelta

_initialized = False

# Cache unificado para todos os endpoints GEE (evita re-chamadas demoradas)
_gee_cache: dict[str, tuple[dict, float]] = {}
_CACHE_TTL = 300  # 5 minutos


def _cache_get(key: str) -> dict | None:
    cached = _gee_cache.get(key)
    if cached and (time.time() - cached[1]) < _CACHE_TTL:
        return cached[0]
    return None


def _cache_set(key: str, value: dict):
    _gee_cache[key] = (value, time.time())

# Extensao global para thumbnails equiretangulares (consistente para MODIS e Landsat)
_GLOBAL_THUMB_REGION = None  # Inicializado apos ee.Initialize()

# Paleta termica padrao reutilizada por todos os endpoints
_THERMAL_PALETTE = [
    "0000FF", "0055FF", "00AAFF", "00FFFF",
    "00FF55", "AAFF00", "FFFF00",
    "FFAA00", "FF5500", "FF0000", "CC0000",
]

# Paleta para anomalias (desvio: azul=abaixo, branco=normal, vermelho=acima)
_ANOMALY_PALETTE = [
    "0000CC", "0044FF", "0088FF", "00CCFF",
    "AAFFAA", "FFFFFF",
    "FFCC00", "FF8800", "FF4400", "FF0000", "AA0000",
]

# Paleta NDVI: solo nu/seco (marrom) -> vegetacao esparsa (amarelo) -> floresta densa (verde escuro)
_NDVI_PALETTE = [
    "8B4513", "A0522D", "CD853F", "D2B48C",
    "DAA520", "F0E68C", "ADFF2F",
    "7CFC00", "32CD32", "228B22", "006400", "003300",
]


def _get_credentials_path() -> str:
    """Retorna o caminho do JSON da Service Account, validando existencia."""
    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not path:
        raise RuntimeError(
            "Variavel GOOGLE_APPLICATION_CREDENTIALS nao definida. "
            "Configure no .env apontando para o JSON da Service Account."
        )
    if not os.path.isfile(path):
        raise RuntimeError(
            f"Arquivo de credenciais nao encontrado: {path}. "
            "Verifique se o JSON da Service Account esta no caminho correto."
        )
    return path


def initialize_gee():
    """
    Inicializa o Earth Engine com credenciais de Service Account.
    Idempotente - so inicializa uma vez.
    """
    global _initialized
    if _initialized:
        return

    cred_path = _get_credentials_path()
    scopes = ["https://www.googleapis.com/auth/earthengine.readonly"]

    credentials = sa.Credentials.from_service_account_file(cred_path, scopes=scopes)
    ee.Initialize(credentials=credentials, opt_url="https://earthengine.googleapis.com")
    _initialized = True

    global _GLOBAL_THUMB_REGION
    _GLOBAL_THUMB_REGION = ee.Geometry.Rectangle(
        [-180, -85, 180, 85], proj="EPSG:4326", geodesic=False
    )
    print("[+] Google Earth Engine inicializado com sucesso.")


def is_initialized() -> bool:
    return _initialized


def _get_modis_collection(days: int) -> tuple:
    """
    Busca colecao MODIS LST com fallback progressivo de janela temporal.
    Retorna (collection_kelvin, img_count, actual_days).
    Processamento no Google - nenhum pixel local.
    """
    end = datetime.utcnow()

    for window in [days, 14, 30, 60]:
        start = end - timedelta(days=window)
        collection = (
            ee.ImageCollection("MODIS/061/MOD11A1")
            .filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            .select("LST_Day_1km")
        )
        # .size().getInfo() retorna um unico inteiro - safe para MaaS
        img_count = collection.size().getInfo()
        if img_count > 0:
            image = collection.mean().multiply(0.02)  # Fator de escala -> Kelvin
            return image, img_count, window

    raise RuntimeError("Nenhuma imagem MODIS LST disponivel nos ultimos 60 dias.")


# ==================== CAMADAS DE VISUALIZACAO ====================

def get_modis_lst_layer(days: int = 7) -> dict:
    """
    Gera tile URL + thumb para MODIS Land Surface Temperature.
    Processamento inteiramente no Google. Retorno: URLs + escalares.
    """
    initialize_gee()

    cache_key = f"modis:{days}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    image, img_count, actual_days = _get_modis_collection(days)

    vis_params = {"min": 250, "max": 330, "palette": _THERMAL_PALETTE}

    # getMapId retorna apenas URL template (string) - zero RAM
    map_id_dict = image.getMapId(vis_params)
    tile_url = map_id_dict["tile_fetcher"].url_format

    # Thumb equiretangular para overlay no globo 3D (projecao global explicita)
    vis_image = image.visualize(**vis_params)
    thumb_url = vis_image.getThumbURL({
        "dimensions": "2048x1024",
        "format": "png",
        "region": _GLOBAL_THUMB_REGION,
        "crs": "EPSG:4326",
    })

    result = {
        "tile_url": tile_url,
        "thumb_url": thumb_url,
        "dataset": "MODIS/061/MOD11A1",
        "band": "LST_Day_1km",
        "period_days": actual_days,
        "images_used": img_count,
        "vis": {
            "min_k": 250,
            "max_k": 330,
            "description": "Land Surface Temperature (Kelvin) - Media dos ultimos {} dias".format(actual_days),
        },
    }
    _cache_set(cache_key, result)
    return result


def get_landsat_thermal_layer(days: int = 30, bbox: list[float] | None = None) -> dict:
    """
    Gera tile URL para Landsat 9 banda termica (~100m resolucao).
    Processamento inteiramente no Google.

    Landsat em resolucao 100m e pesado demais para thumb global.
    Se bbox fornecido, filtra espacialmente e gera thumb equiretangular global
    com dados apenas na regiao (resto transparente via PNG alpha).
    """
    initialize_gee()

    cache_key = f"landsat:{days}:{tuple(bbox) if bbox else None}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    end = datetime.utcnow()

    # Filtro espacial (Landsat precisa limitar regiao para performance)
    # Bboxes que cobrem >300 graus de longitude sao "globais" - skip clip
    region_filter = None
    is_regional = False
    if bbox and len(bbox) == 4:
        width = abs(bbox[2] - bbox[0])
        if width < 300:
            region_filter = ee.Geometry.Rectangle(bbox)
            is_regional = True

    for window in [days, 60, 90, 120]:
        start = end - timedelta(days=window)
        collection = (
            ee.ImageCollection("LANDSAT/LC09/C02/T1_L2")
            .filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            .filter(ee.Filter.lt("CLOUD_COVER", 30))
            .select("ST_B10")
        )
        if region_filter:
            collection = collection.filterBounds(region_filter)

        img_count = collection.size().getInfo()
        if img_count > 0:
            image = collection.median().multiply(0.00341802).add(149.0)
            vis_params = {
                "min": 270, "max": 320,
                "palette": ["0000FF", "00AAFF", "00FFAA", "FFFF00", "FF8800", "FF0000", "AA0000"],
            }
            map_id_dict = image.getMapId(vis_params)
            # Thumb equiretangular global com dados apenas na regiao clippada
            # Pixels fora da regiao ficam transparentes (PNG alpha)
            thumb_url = None
            if is_regional:
                vis_image = image.clip(region_filter).visualize(**vis_params)
                thumb_url = vis_image.getThumbURL({
                    "dimensions": "1024x512",
                    "format": "png",
                    "region": _GLOBAL_THUMB_REGION,
                    "crs": "EPSG:4326",
                })
            result = {
                "tile_url": map_id_dict["tile_fetcher"].url_format,
                "thumb_url": thumb_url,
                "dataset": "LANDSAT/LC09/C02/T1_L2",
                "band": "ST_B10",
                "period_days": window,
                "images_used": img_count,
                "vis": {
                    "min_k": 270, "max_k": 320,
                    "description": "Surface Temperature Landsat 9 (~100m) - Mediana dos ultimos {} dias".format(window),
                },
            }
            _cache_set(cache_key, result)
            return result

    raise RuntimeError("Nenhuma imagem Landsat 9 disponivel nos ultimos 120 dias.")


# ==================== CAMADA DE VEGETACAO (NDVI - Landsat 8) ====================

def get_vegetation_layer(days: int = 30, bbox: list[float] | None = None) -> dict:
    """
    Gera tile URL + thumb para NDVI (Normalized Difference Vegetation Index)
    usando USGS Landsat 8 Collection 2 Tier 1 TOA.

    DOUTRINA MaaS: normalizedDifference() executa no servidor Google.
    Retorno: URLs + escalares. Nenhum pixel transita para RAM local.

    NDVI = (NIR - Red) / (NIR + Red) = normalizedDifference(['B5', 'B4'])
    Valores: -1 (agua/nuvem) a +1 (floresta densa saudavel)
    """
    initialize_gee()

    cache_key = f"vegetation:{days}:{tuple(bbox) if bbox else None}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    end = datetime.utcnow()

    region_filter = None
    if bbox and len(bbox) == 4:
        width = abs(bbox[2] - bbox[0])
        if width < 300:
            region_filter = ee.Geometry.Rectangle(bbox)

    for window in [days, 60, 90, 120]:
        start = end - timedelta(days=window)
        collection = (
            ee.ImageCollection("LANDSAT/LC08/C02/T1_TOA")
            .filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            .filter(ee.Filter.lt("CLOUD_COVER", 30))
            .select(["B5", "B4"])
        )
        if region_filter:
            collection = collection.filterBounds(region_filter)

        img_count = collection.size().getInfo()  # unico escalar
        if img_count > 0:
            # NDVI calculado inteiramente no servidor Google
            ndvi = collection.median().normalizedDifference(["B5", "B4"])

            vis_params = {"min": -0.2, "max": 0.9, "palette": _NDVI_PALETTE}
            map_id_dict = ndvi.getMapId(vis_params)
            tile_url = map_id_dict["tile_fetcher"].url_format

            # Thumb equiretangular para overlay no globo 3D
            # SEM clip: filterBounds ja limita a colecao a regiao.
            # Clip em canvas global causava pixelacao (poucos px com dados).
            vis_image = ndvi.visualize(**vis_params)
            thumb_url = vis_image.getThumbURL({
                "dimensions": "2048x1024",
                "format": "png",
                "region": _GLOBAL_THUMB_REGION,
                "crs": "EPSG:4326",
            })

            result = {
                "tile_url": tile_url,
                "thumb_url": thumb_url,
                "dataset": "LANDSAT/LC08/C02/T1_TOA",
                "band": "NDVI (B5-B4)",
                "period_days": window,
                "images_used": img_count,
                "vis": {
                    "min": -0.2,
                    "max": 0.9,
                    "description": "NDVI Landsat 8 - Mediana dos ultimos {} dias".format(window),
                },
            }
            _cache_set(cache_key, result)
            return result

    raise RuntimeError("Nenhuma imagem Landsat 8 disponivel nos ultimos 120 dias.")


# ==================== ANALISE REGIONAL VEGETACAO (MaaS: processamento no Google) ====================

def analyze_vegetation_region(bbox: list[float], days: int = 30) -> dict:
    """
    Analise de saude da vegetacao (NDVI) de uma regiao via Landsat 8.

    DOUTRINA MaaS ESTRITA:
    - normalizedDifference() executa no servidor Google
    - reduceRegion() retorna apenas escalares (~6 numeros)
    - getMapId() retorna apenas URL template (string)
    - Nenhum array ou pixel transita para RAM local

    Args:
        bbox: [west, south, east, north] em graus decimais
        days: janela temporal (1-120)

    Returns:
        dict com tile_url, thumb_url, estatisticas NDVI, metadata
    """
    initialize_gee()

    cache_key = f"veg_analysis:{tuple(bbox)}:{days}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    west, south, east, north = bbox
    region = ee.Geometry.Rectangle([west, south, east, north])
    end = datetime.utcnow()

    # --- Colecao atual com fallback progressivo ---
    ndvi_image = None
    img_count = 0
    actual_days = days

    for window in [days, 60, 90, 120]:
        start = end - timedelta(days=window)
        collection = (
            ee.ImageCollection("LANDSAT/LC08/C02/T1_TOA")
            .filterDate(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            .filter(ee.Filter.lt("CLOUD_COVER", 30))
            .filterBounds(region)
            .select(["B5", "B4"])
        )
        img_count = collection.size().getInfo()
        if img_count > 0:
            # NDVI no servidor Google
            ndvi_image = collection.median().normalizedDifference(["B5", "B4"])
            actual_days = window
            break

    if ndvi_image is None:
        raise RuntimeError("Nenhuma imagem Landsat 8 disponivel nos ultimos 120 dias para a regiao.")

    # --- Estatisticas agregadas via reduceRegion (retorna escalares) ---
    stats_ndvi = ndvi_image.reduceRegion(
        reducer=ee.Reducer.mean()
            .combine(ee.Reducer.max(), sharedInputs=True)
            .combine(ee.Reducer.min(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=region,
        scale=30,  # resolucao Landsat 8: 30m
        maxPixels=1e7,
        bestEffort=True,
    ).getInfo()

    # Conta pixels com vegetacao saudavel (NDVI > 0.4) e estressada (NDVI < 0.2)
    healthy_mask = ndvi_image.gt(0.4)
    stressed_mask = ndvi_image.lt(0.2)

    pixel_stats = healthy_mask.addBands(stressed_mask).rename(["healthy", "stressed"]).reduceRegion(
        reducer=ee.Reducer.sum().combine(ee.Reducer.count(), sharedInputs=True),
        geometry=region,
        scale=30,
        maxPixels=1e7,
        bestEffort=True,
    ).getInfo()

    # Extrai escalares
    def _safe(d, key, default=0.0):
        v = d.get(key)
        return round(float(v), 4) if v is not None else default

    ndvi_mean = _safe(stats_ndvi, "nd_mean")
    ndvi_max = _safe(stats_ndvi, "nd_max")
    ndvi_min = _safe(stats_ndvi, "nd_min")
    ndvi_stddev = _safe(stats_ndvi, "nd_stdDev")

    healthy_pixels = _safe(pixel_stats, "healthy_sum", 0)
    total_pixels = _safe(pixel_stats, "healthy_count", 1)
    stressed_pixels = _safe(pixel_stats, "stressed_sum", 0)
    healthy_pct = round((healthy_pixels / max(total_pixels, 1)) * 100, 2)
    stressed_pct = round((stressed_pixels / max(total_pixels, 1)) * 100, 2)

    statistics = {
        "ndvi_media": ndvi_mean,
        "ndvi_max": ndvi_max,
        "ndvi_min": ndvi_min,
        "ndvi_stddev": ndvi_stddev,
        "vegetacao_saudavel_pct": healthy_pct,
        "vegetacao_estressada_pct": stressed_pct,
        "healthy_pixels": int(healthy_pixels),
        "stressed_pixels": int(stressed_pixels),
        "total_pixels": int(total_pixels),
    }

    # --- Tile URL para visualizacao (somente URL, zero dados) ---
    vis_params = {"min": -0.2, "max": 0.9, "palette": _NDVI_PALETTE}
    map_ndvi = ndvi_image.getMapId(vis_params)
    tile_url = map_ndvi["tile_fetcher"].url_format

    # Thumb equiretangular global - SEM clip
    # A colecao ja foi filtrada por filterBounds(region), entao o median
    # contem dados naturalmente concentrados na regiao.
    # Clip forçava poucos pixels num canvas 2048x1024 → pixelado no globo.
    vis_image = ndvi_image.visualize(**vis_params)
    thumb_url = vis_image.getThumbURL({
        "dimensions": "2048x1024",
        "format": "png",
        "region": _GLOBAL_THUMB_REGION,
        "crs": "EPSG:4326",
    })

    result = {
        "tile_url": tile_url,
        "thumb_url": thumb_url,
        "statistics": statistics,
        "dataset": "LANDSAT/LC08/C02/T1_TOA",
        "band": "NDVI (B5-B4)",
        "period_days": actual_days,
        "images_used": img_count,
        "bbox": bbox,
        "vis": {
            "min": -0.2,
            "max": 0.9,
            "description": "NDVI - valores proximos a 1 indicam floresta saudavel",
        },
    }
    _cache_set(cache_key, result)
    return result


# ==================== ANALISE REGIONAL (MaaS: processamento no Google) ====================

def analyze_thermal_region(bbox: list[float], days: int = 7) -> dict:
    """
    Analise termica de uma regiao (bounding box).

    DOUTRINA MaaS ESTRITA:
    - reduceRegion() executa no servidor Google e retorna apenas escalares
    - getMapId() retorna apenas uma URL template (string)
    - getThumbURL() retorna apenas uma URL (string)
    - Nenhum .getInfo() e chamado em objetos grandes (imagens/colecoes)
    - Unico .getInfo() e em dicionarios de reducao (~6 numeros)

    Args:
        bbox: [west, south, east, north] em graus decimais
        days: janela temporal

    Returns:
        dict com tile_url, thumb_url, estatisticas agregadas, metadata
    """
    initialize_gee()

    cache_key = f"analysis:{tuple(bbox)}:{days}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    west, south, east, north = bbox
    region = ee.Geometry.Rectangle([west, south, east, north])

    # --- Periodo atual ---
    image_current, img_count, actual_days = _get_modis_collection(days)

    # --- Baseline historica (mesmo mes, 5 anos anteriores) ---
    # Processamento inteiro no Google: filtra, agrega, subtrai
    now = datetime.utcnow()
    baseline_collection = ee.ImageCollection([])
    for y in range(1, 6):
        year = now.year - y
        m_start = f"{year}-{now.month:02d}-01"
        m_end_month = now.month + 1 if now.month < 12 else 1
        m_end_year = year if now.month < 12 else year + 1
        m_end = f"{m_end_year}-{m_end_month:02d}-01"
        yearly = (
            ee.ImageCollection("MODIS/061/MOD11A1")
            .filterDate(m_start, m_end)
            .select("LST_Day_1km")
        )
        baseline_collection = baseline_collection.merge(yearly)

    baseline_image = baseline_collection.mean().multiply(0.02)  # Kelvin

    # Anomalia = atual - baseline (processado no Google)
    anomaly_image = image_current.subtract(baseline_image)

    # --- Estatisticas agregadas via reduceRegion (retorna ~6 escalares) ---
    # Unico .getInfo() no pipeline - retorna dict com numeros puros
    stats_current = image_current.reduceRegion(
        reducer=ee.Reducer.mean()
            .combine(ee.Reducer.max(), sharedInputs=True)
            .combine(ee.Reducer.min(), sharedInputs=True)
            .combine(ee.Reducer.stdDev(), sharedInputs=True),
        geometry=region,
        scale=1000,
        maxPixels=1e7,
        bestEffort=True,
    ).getInfo()

    stats_anomaly = anomaly_image.reduceRegion(
        reducer=ee.Reducer.mean()
            .combine(ee.Reducer.max(), sharedInputs=True)
            .combine(ee.Reducer.min(), sharedInputs=True),
        geometry=region,
        scale=1000,
        maxPixels=1e7,
        bestEffort=True,
    ).getInfo()

    # Conta pixels acima de 330K (hotspots) - resultado: 1 escalar
    hotspot_mask = image_current.gt(330)
    hotspot_stats = hotspot_mask.reduceRegion(
        reducer=ee.Reducer.sum().combine(ee.Reducer.count(), sharedInputs=True),
        geometry=region,
        scale=1000,
        maxPixels=1e7,
        bestEffort=True,
    ).getInfo()

    # Extrai escalares dos dicts de reducao
    def _safe(d, key, default=0.0):
        v = d.get(key)
        return round(float(v), 2) if v is not None else default

    hotspot_pixels = _safe(hotspot_stats, "LST_Day_1km_sum", 0)
    total_pixels = _safe(hotspot_stats, "LST_Day_1km_count", 1)
    hotspot_pct = round((hotspot_pixels / max(total_pixels, 1)) * 100, 2)

    statistics = {
        "temp_media_k": _safe(stats_current, "LST_Day_1km_mean"),
        "temp_max_k": _safe(stats_current, "LST_Day_1km_max"),
        "temp_min_k": _safe(stats_current, "LST_Day_1km_min"),
        "temp_stddev_k": _safe(stats_current, "LST_Day_1km_stdDev"),
        "temp_media_c": round(_safe(stats_current, "LST_Day_1km_mean") - 273.15, 2),
        "temp_max_c": round(_safe(stats_current, "LST_Day_1km_max") - 273.15, 2),
        "temp_min_c": round(_safe(stats_current, "LST_Day_1km_min") - 273.15, 2),
        "anomalia_media_k": _safe(stats_anomaly, "LST_Day_1km_mean"),
        "anomalia_max_k": _safe(stats_anomaly, "LST_Day_1km_max"),
        "anomalia_min_k": _safe(stats_anomaly, "LST_Day_1km_min"),
        "hotspot_pct": hotspot_pct,
        "hotspot_pixels": int(hotspot_pixels),
        "total_pixels": int(total_pixels),
    }

    # --- Tile URLs para visualizacao (somente URLs, zero dados) ---

    # Range dinamico baseado nos dados reais da regiao (melhor contraste de cores)
    region_min = _safe(stats_current, "LST_Day_1km_min", 250)
    region_max = _safe(stats_current, "LST_Day_1km_max", 330)
    margin = max(3, (region_max - region_min) * 0.1)  # 10% de margem, minimo 3K
    vis_min = round(region_min - margin)
    vis_max = round(region_max + margin)

    # Camada LST atual com range dinamico
    vis_current = {"min": vis_min, "max": vis_max, "palette": _THERMAL_PALETTE}
    map_current = image_current.getMapId(vis_current)
    tile_url_lst = map_current["tile_fetcher"].url_format

    # Camada de anomalia
    anom_min = _safe(stats_anomaly, "LST_Day_1km_min", -10)
    anom_max = _safe(stats_anomaly, "LST_Day_1km_max", 10)
    anom_range = max(abs(anom_min), abs(anom_max), 2)  # simetrico, minimo 2K
    vis_anomaly = {"min": -anom_range, "max": anom_range, "palette": _ANOMALY_PALETTE}
    map_anomaly = anomaly_image.getMapId(vis_anomaly)
    tile_url_anomaly = map_anomaly["tile_fetcher"].url_format

    # Thumb equiretangular global para overlay no globo
    # SEM clip: MODIS e global, mostra o mundo todo mas com range
    # dinamico otimizado para a regiao (melhor contraste local)
    vis_image = image_current.visualize(**vis_current)
    thumb_url = vis_image.getThumbURL({
        "dimensions": "2048x1024",
        "format": "png",
        "region": _GLOBAL_THUMB_REGION,
        "crs": "EPSG:4326",
    })

    # Thumb da anomalia (global, range dinamico simetrico)
    vis_anom_image = anomaly_image.visualize(**vis_anomaly)
    thumb_url_anomaly = vis_anom_image.getThumbURL({
        "dimensions": "2048x1024",
        "format": "png",
        "region": _GLOBAL_THUMB_REGION,
        "crs": "EPSG:4326",
    })

    result = {
        "tile_url_lst": tile_url_lst,
        "tile_url_anomaly": tile_url_anomaly,
        "thumb_url": thumb_url,
        "thumb_url_anomaly": thumb_url_anomaly,
        "statistics": statistics,
        "dataset": "MODIS/061/MOD11A1",
        "period_days": actual_days,
        "images_used": img_count,
        "bbox": bbox,
        "baseline": "mesmo mes, 5 anos anteriores",
        "vis": {
            "min_k": vis_min,
            "max_k": vis_max,
            "min_c": round(vis_min - 273.15, 1),
            "max_c": round(vis_max - 273.15, 1),
        },
        "vis_anomaly": {
            "min_k": round(-anom_range, 1),
            "max_k": round(anom_range, 1),
        },
    }
    _cache_set(cache_key, result)
    return result
