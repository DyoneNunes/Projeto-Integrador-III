"""Testes de schema, constraints e índices do PostgreSQL."""
import os
import pytest
import psycopg2

DB_CONNECTION = os.getenv(
    "DB_CONNECTION",
    "postgresql://postgres:password_sentinela@localhost:5436/postgres"
)


@pytest.fixture
def conn():
    c = psycopg2.connect(DB_CONNECTION)
    yield c
    c.close()


def test_schema_sentinela_existe(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'sentinela_ambiental';")
        assert cur.fetchone() is not None


def test_tabelas_existem(conn):
    tabelas = ['sensors', 'sensor_readings', 'alerts_history', 'ai_predictions']
    with conn.cursor() as cur:
        for tabela in tabelas:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'sentinela_ambiental' AND table_name = %s;
            """, (tabela,))
            assert cur.fetchone() is not None, f"Tabela {tabela} não encontrada"


def test_sensor_padrao_existe(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, name FROM sentinela_ambiental.sensors WHERE name = 'NASA_FIRMS_VIIRS';")
        row = cur.fetchone()
        assert row is not None
        assert row[1] == 'NASA_FIRMS_VIIRS'


def test_indice_timestamp_existe(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT indexname FROM pg_indexes
            WHERE schemaname = 'sentinela_ambiental'
            AND tablename = 'sensor_readings'
            AND indexname = 'idx_sensor_readings_timestamp';
        """)
        assert cur.fetchone() is not None, "Índice idx_sensor_readings_timestamp não encontrado"


def test_unique_constraint_ai_predictions(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_schema = 'sentinela_ambiental'
            AND table_name = 'ai_predictions'
            AND constraint_type = 'UNIQUE';
        """)
        row = cur.fetchone()
        assert row is not None, "UNIQUE constraint em ai_predictions não encontrada"


def test_fk_alerts_history(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT constraint_name FROM information_schema.table_constraints
            WHERE table_schema = 'sentinela_ambiental'
            AND table_name = 'alerts_history'
            AND constraint_type = 'FOREIGN KEY';
        """)
        assert cur.fetchone() is not None, "FK em alerts_history não encontrada"
