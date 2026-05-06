"""Testes dos endpoints FastAPI — requer containers Docker rodando."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
os.environ.setdefault("DB_CONNECTION", "postgresql://postgres:password_sentinela@localhost:5436/postgres")

from fastapi.testclient import TestClient
from api import app

client = TestClient(app)


def test_get_alerts_retorna_json():
    r = client.get("/api/alerts?hours=24")
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "alerts" in data
    assert isinstance(data["alerts"], list)


def test_get_alerts_limite_horas():
    r1 = client.get("/api/alerts?hours=1")
    r168 = client.get("/api/alerts?hours=168")
    assert r1.status_code == 200
    assert r168.status_code == 200
    assert r168.json()["count"] >= r1.json()["count"]


def test_get_alerts_deduplicado():
    r = client.get("/api/alerts?hours=24")
    alerts = r.json()["alerts"]
    if len(alerts) > 1:
        coords = [(round(a["lat"], 3), round(a["lng"], 3)) for a in alerts]
        assert len(coords) == len(set(coords)), "Coordenadas duplicadas encontradas"


def test_get_stats_campos():
    r = client.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_24h" in data
    assert "critical_24h" in data
    assert "max_frp" in data
    assert "avg_confidence" in data


def test_get_stats_retorna_numeros():
    r = client.get("/api/stats")
    data = r.json()
    assert isinstance(data["total_24h"], (int, float))
    assert isinstance(data["max_frp"], (int, float))


def test_get_predictions_campos():
    r = client.get("/api/predictions?hours=24")
    assert r.status_code == 200
    data = r.json()
    assert "count" in data
    assert "fire_detected" in data
    assert "predictions" in data


def test_get_predictions_thermal_type():
    r = client.get("/api/predictions?hours=168")
    data = r.json()
    for pred in data.get("predictions", []):
        # thermal_type não está no endpoint de predictions, apenas no alerts
        assert "prediction_class" in pred
        assert pred["prediction_class"] in (0, 1)


def test_serve_index():
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
