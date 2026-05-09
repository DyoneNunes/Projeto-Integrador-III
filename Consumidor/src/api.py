"""
Sentinela Ambiental - API REST (FastAPI)
Serve os dados de alertas térmicos e o frontend 3D.
"""
import os
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

DB_CONNECTION = os.getenv("DB_CONNECTION")

def get_db():
    """Retorna conexão com o PostgreSQL."""
    return psycopg2.connect(DB_CONNECTION)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
