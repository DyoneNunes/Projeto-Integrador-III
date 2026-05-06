"""
Fixtures compartilhadas para todos os testes do Consumidor.
Requer containers Docker rodando (docker compose up -d).
"""
import os
import sys
import pytest
import psycopg2
import psycopg2.extras

# Adiciona src/ ao path para importar módulos do projeto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

DB_CONNECTION = os.getenv(
    "DB_CONNECTION",
    "postgresql://postgres:password_sentinela@localhost:5436/postgres"
)


@pytest.fixture
def db_conn():
    """Conexão ao PostgreSQL do Docker (porta 5436)."""
    conn = psycopg2.connect(DB_CONNECTION)
    conn.autocommit = False
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
def db_cursor(db_conn):
    """Cursor com RealDictCursor para queries de teste."""
    with db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        yield cur


@pytest.fixture
def fastapi_client():
    """TestClient do FastAPI."""
    os.environ.setdefault("DB_CONNECTION", DB_CONNECTION)
    from httpx import ASGITransport
    from api import app
    from httpx import Client
    transport = ASGITransport(app=app)
    with Client(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_firms_records():
    """Dados simulando registros NASA FIRMS."""
    return [
        {'id': 1, 'lat': -10.0, 'lon': -50.0, 'temp': 380.0, 'frp': 35.0, 'conf': 95, 'type': 0},
        {'id': 2, 'lat': 60.5, 'lon': 100.0, 'temp': 250.0, 'frp': 0.0, 'conf': 90, 'type': 1},
        {'id': 3, 'lat': -15.0, 'lon': -47.0, 'temp': 310.0, 'frp': 5.0, 'conf': 75, 'type': 0},
        {'id': 4, 'lat': 0.0, 'lon': 20.0, 'temp': 295.0, 'frp': 12.0, 'conf': 85, 'type': 0},
        {'id': 5, 'lat': -75.0, 'lon': 0.0, 'temp': 230.0, 'frp': 0.0, 'conf': 88, 'type': 1},
    ]


@pytest.fixture
def sample_features():
    """Feature vectors simulados (sem reading_id)."""
    return [
        (-10.0, -50.0, 35.0, 380.0, 95.0, 14.0, 8.0, 2.0),   # Fogo intenso
        (60.5, 100.0, 0.0, 250.0, 90.0, 3.0, 1.0, 0.0),       # Frio polar
        (-15.0, -47.0, 5.0, 310.0, 75.0, 10.0, 6.0, 1.0),     # Borderline
        (0.0, 20.0, 12.0, 295.0, 85.0, 14.0, 9.0, 0.0),       # Limite calor
        (-75.0, 0.0, 0.0, 230.0, 88.0, 22.0, 7.0, 0.0),       # Frio extremo
    ]
