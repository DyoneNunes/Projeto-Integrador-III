"""
Sentinela Ambiental - API REST (FastAPI)
Serve os dados de alertas térmicos, camadas GEE e o frontend 3D.

DOUTRINA MaaS: O backend NAO aloca matrizes geoespaciais em RAM local.
Processamento pesado e delegado ao Google Earth Engine (servidores remotos).
FastAPI apenas roteia instrucoes e devolve escalares/URLs.
"""
import os
import asyncio
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import psycopg2
import psycopg2.extras
import requests as http_requests
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

DB_CONNECTION = os.getenv("DB_CONNECTION")

# Flag de disponibilidade do GEE (graceful degradation)
_gee_available = False

def get_db():
    """Retorna conexão com o PostgreSQL."""
    return psycopg2.connect(DB_CONNECTION)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _gee_available
    try:
        from . import gee_service
        gee_service.initialize_gee()
        _gee_available = True
        print("[+] GEE disponivel - endpoints /api/gee/* ativos.")
    except Exception as e:
        print(f"[!] GEE indisponivel ({e}). Endpoints /api/gee/* retornarao erro.")
    yield


app = FastAPI(title="Sentinela Ambiental API", lifespan=lifespan)


@app.get("/api/alerts")
def get_alerts(hours: int = Query(default=24, ge=1, le=168)):
    """
    Retorna alertas térmicos das últimas N horas.
    JOIN entre sensor_readings e alerts_history.
    """
    query = """
        WITH dedup AS (
            SELECT DISTINCT ON (ROUND(sr.latitude::numeric, 3), ROUND(sr.longitude::numeric, 3))
                sr.latitude AS lat,
                sr.longitude AS lng,
                sr.frp,
                sr.temperature_k,
                sr.confidence,
                sr.satellite_type,
                ah.severity,
                ah.alert_type,
                sr.reading_timestamp
            FROM sentinela_ambiental.sensor_readings sr
            JOIN sentinela_ambiental.alerts_history ah ON sr.id = ah.reading_id
            WHERE sr.reading_timestamp >= NOW() - INTERVAL '%s hours'
            ORDER BY ROUND(sr.latitude::numeric, 3), ROUND(sr.longitude::numeric, 3), sr.reading_timestamp DESC
        )
        SELECT * FROM dedup
        ORDER BY reading_timestamp DESC
        LIMIT 5000
    """
    conn = None
    try:
        conn = get_db()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (hours,))
            rows = cur.fetchall()

        results = []
        for row in rows:
            results.append({
                "lat": row["lat"],
                "lng": row["lng"],
                "frp": row["frp"] or 0,
                "temperature_k": row["temperature_k"],
                "confidence": row["confidence"],
                "thermal_type": "heat" if (row["satellite_type"] or 0) == 0 else "cold",
                "severity": row["severity"],
                "alert_type": row["alert_type"],
                "timestamp": row["reading_timestamp"].isoformat() if row["reading_timestamp"] else None,
            })
        return {"count": len(results), "alerts": results}
    except Exception as e:
        return {"count": 0, "alerts": [], "error": str(e)}
    finally:
        if conn:
            conn.close()


@app.get("/api/stats")
def get_stats():
    """KPIs rápidos para o painel."""
    query = """
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE ah.severity = 'CRITICAL') AS critical,
            MAX(sr.frp) AS max_frp,
            AVG(sr.confidence) AS avg_confidence
        FROM sentinela_ambiental.sensor_readings sr
        JOIN sentinela_ambiental.alerts_history ah ON sr.id = ah.reading_id
        WHERE sr.reading_timestamp >= NOW() - INTERVAL '24 hours'
    """
    conn = None
    try:
        conn = get_db()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            row = cur.fetchone()
        if not row or row["total"] is None or row["total"] == 0:
            return {"total_24h": 0, "critical_24h": 0, "max_frp": 0, "avg_confidence": 0}
        return {
            "total_24h": row["total"],
            "critical_24h": row["critical"],
            "max_frp": round(row["max_frp"] or 0, 2),
            "avg_confidence": round(row["avg_confidence"] or 0, 1),
        }
    except Exception as e:
        return {"total_24h": 0, "critical_24h": 0, "max_frp": 0, "avg_confidence": 0, "error": str(e)}
    finally:
        if conn:
            conn.close()


@app.get("/api/predictions")
def get_predictions(hours: int = Query(default=24, ge=1, le=168)):
    """
    Retorna predições da IA com dados do sensor.
    JOIN entre ai_predictions e sensor_readings.
    """
    query = """
        SELECT
            sr.latitude AS lat,
            sr.longitude AS lng,
            sr.frp,
            sr.temperature_k,
            sr.confidence,
            ap.prediction_class,
            ap.prediction_probability,
            ap.urgency_score,
            ap.model_version,
            ap.predicted_at
        FROM sentinela_ambiental.ai_predictions ap
        JOIN sentinela_ambiental.sensor_readings sr ON ap.reading_id = sr.id
        WHERE ap.predicted_at >= NOW() - INTERVAL '%s hours'
        ORDER BY ap.urgency_score DESC
        LIMIT 5000
    """
    conn = None
    try:
        conn = get_db()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, (hours,))
            rows = cur.fetchall()

        results = []
        for row in rows:
            results.append({
                "lat": row["lat"],
                "lng": row["lng"],
                "frp": row["frp"] or 0,
                "temperature_k": row["temperature_k"],
                "confidence": row["confidence"],
                "prediction_class": row["prediction_class"],
                "probability": round(row["prediction_probability"], 4),
                "urgency": round(row["urgency_score"] or 0, 4),
                "model_version": row["model_version"],
                "timestamp": row["predicted_at"].isoformat() if row["predicted_at"] else None,
            })

        fire_count = sum(1 for r in results if r["prediction_class"] == 1)
        return {"count": len(results), "fire_detected": fire_count, "predictions": results}
    except Exception as e:
        return {"count": 0, "fire_detected": 0, "predictions": [], "error": str(e)}
    finally:
        if conn:
            conn.close()


# ==================== GEE ENDPOINTS ====================

@app.get("/api/gee/camada-termica")
async def get_thermal_layer(
    dataset: str = Query(default="modis", pattern="^(modis|landsat)$"),
    days: int = Query(default=7, ge=1, le=90),
    bbox: str = Query(default=None),
):
    """
    Retorna tile URL do Google Earth Engine para camada termica.
    Processamento ocorre no Google - nenhum dado bruto e baixado.

    bbox opcional: "west,south,east,north" para Landsat (necessario para performance).
    """
    if not _gee_available:
        return {
            "error": "Google Earth Engine nao configurado. Verifique GOOGLE_APPLICATION_CREDENTIALS.",
            "available": False,
        }

    try:
        from . import gee_service

        if dataset == "landsat":
            parsed_bbox = None
            if bbox:
                parsed_bbox = [float(x) for x in bbox.split(",")]
            result = await asyncio.to_thread(
                gee_service.get_landsat_thermal_layer, days=days, bbox=parsed_bbox
            )
        else:
            result = await asyncio.to_thread(gee_service.get_modis_lst_layer, days=days)

        return {"available": True, **result}

    except Exception as e:
        return {"available": False, "error": str(e)}


class AnaliseRegionalRequest(BaseModel):
    """Payload para analise termica regional."""
    bbox: list[float]  # [west, south, east, north]
    days: int = 7


@app.post("/api/gee/analise/temperatura")
async def analyze_temperature(req: AnaliseRegionalRequest):
    """
    Analise termica regional com estatisticas e camada de anomalia.

    DOUTRINA MaaS:
    - FastAPI apenas monta a instrucao e envia ao GEE
    - GEE processa na RAM dos servidores Google (reduceRegion, getMapId)
    - Retorno: escalares (media, max, min, anomalia%) + URLs de tiles
    - Zero alocacao de arrays/rasters em memoria local
    """
    if not _gee_available:
        return {
            "error": "Google Earth Engine nao configurado.",
            "available": False,
        }

    if len(req.bbox) != 4:
        return {"error": "bbox deve ter 4 valores: [west, south, east, north]", "available": False}

    try:
        from . import gee_service

        # Executa em thread separada para nao bloquear o event loop do Uvicorn
        result = await asyncio.to_thread(
            gee_service.analyze_thermal_region,
            bbox=req.bbox,
            days=max(1, min(req.days, 90)),
        )

        return {"available": True, **result}

    except Exception as e:
        return {"available": False, "error": str(e)}


class AnaliseVegetacaoRequest(BaseModel):
    """Payload para analise de vegetacao regional."""
    bbox: list[float]  # [west, south, east, north]
    days: int = 30


@app.post("/api/gee/analise/vegetacao")
async def analyze_vegetation(req: AnaliseVegetacaoRequest):
    """
    Analise de saude da vegetacao (NDVI) regional via Landsat 8.

    DOUTRINA MaaS:
    - FastAPI apenas monta a instrucao e envia ao GEE
    - GEE calcula normalizedDifference(['B5', 'B4']) nos servidores Google
    - reduceRegion() retorna apenas escalares (media, max, min NDVI)
    - Zero alocacao de arrays/rasters em memoria local
    """
    if not _gee_available:
        return {
            "error": "Google Earth Engine nao configurado.",
            "available": False,
        }

    if len(req.bbox) != 4:
        return {"error": "bbox deve ter 4 valores: [west, south, east, north]", "available": False}

    try:
        from . import gee_service

        result = await asyncio.to_thread(
            gee_service.analyze_vegetation_region,
            bbox=req.bbox,
            days=max(1, min(req.days, 120)),
        )

        return {"available": True, **result}

    except Exception as e:
        return {"available": False, "error": str(e)}


@app.get("/api/gee/proxy-thumb")
async def proxy_gee_thumb(url: str = Query(...)):
    """
    Proxy para thumbnails do GEE. Evita problemas de CORS e URLs expiradas.
    O backend baixa a imagem (streaming, sem armazenar em RAM) e repassa ao frontend.
    """
    if not url.startswith("https://earthengine.googleapis.com/"):
        return Response(status_code=400, content="URL invalida")

    try:
        resp = await asyncio.to_thread(
            http_requests.get, url, timeout=120, stream=True
        )
        if resp.status_code != 200:
            return Response(status_code=resp.status_code, content="Erro ao buscar thumb do GEE")

        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "image/png"),
            headers={"Cache-Control": "public, max-age=300"},
        )
    except Exception as e:
        return Response(status_code=502, content=str(e))


@app.get("/api/gee/status")
async def gee_status():
    """Verifica se o GEE esta inicializado e disponivel."""
    return {"available": _gee_available}


# ==================== STATIC FILES ====================

# Serve o frontend estático
# Workdir no container é /app, static montado em /app/static
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")
if not os.path.isdir(static_dir):
    static_dir = "/app/static"

app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def serve_index():
    index_path = os.path.join(static_dir, "index.html")
    return FileResponse(index_path)
