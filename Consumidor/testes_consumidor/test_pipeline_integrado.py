"""Testes end-to-end do pipeline — requer containers Docker rodando."""
import os
import pytest
import psycopg2
import psycopg2.extras

DB_CONNECTION = os.getenv(
    "DB_CONNECTION",
    "postgresql://postgres:password_sentinela@localhost:5436/postgres"
)


@pytest.fixture
def conn():
    c = psycopg2.connect(DB_CONNECTION)
    c.autocommit = False
    yield c
    c.rollback()
    c.close()


def test_sensor_reading_inserido(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sentinela_ambiental.sensor_readings
            (sensor_id, latitude, longitude, temperature_k, frp, satellite_type, confidence)
            VALUES (1, -10.0, -50.0, 380.0, 35.0, 0, 95) RETURNING id;
        """)
        reading_id = cur.fetchone()[0]
        assert reading_id is not None
        assert isinstance(reading_id, int)


def test_alert_history_vinculado(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sentinela_ambiental.sensor_readings
            (sensor_id, latitude, longitude, temperature_k, frp, satellite_type, confidence)
            VALUES (1, -10.0, -50.0, 380.0, 35.0, 0, 95) RETURNING id;
        """)
        reading_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO sentinela_ambiental.alerts_history
            (reading_id, alert_type, severity, description)
            VALUES (%s, 'THERMAL_ANOMALY', 'CRITICAL', 'Teste') RETURNING id;
        """, (reading_id,))
        alert_id = cur.fetchone()[0]
        assert alert_id is not None


def test_predicao_vinculada(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sentinela_ambiental.sensor_readings
            (sensor_id, latitude, longitude, temperature_k, frp, satellite_type, confidence)
            VALUES (1, -10.0, -50.0, 380.0, 35.0, 0, 95) RETURNING id;
        """)
        reading_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO sentinela_ambiental.ai_predictions
            (reading_id, model_version, prediction_class, prediction_probability, urgency_score)
            VALUES (%s, 'v1.0.0-test', 1, 0.85, 0.72) RETURNING id;
        """, (reading_id,))
        pred_id = cur.fetchone()[0]
        assert pred_id is not None


def test_unique_constraint_predicao(conn):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO sentinela_ambiental.sensor_readings
            (sensor_id, latitude, longitude, temperature_k, frp, satellite_type, confidence)
            VALUES (1, -10.0, -50.0, 380.0, 35.0, 0, 95) RETURNING id;
        """)
        reading_id = cur.fetchone()[0]
        cur.execute("""
            INSERT INTO sentinela_ambiental.ai_predictions
            (reading_id, model_version, prediction_class, prediction_probability, urgency_score)
            VALUES (%s, 'v1.0.0-test', 1, 0.85, 0.72);
        """, (reading_id,))
        # Segunda inserção com mesmo reading_id deve falhar
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute("""
                INSERT INTO sentinela_ambiental.ai_predictions
                (reading_id, model_version, prediction_class, prediction_probability, urgency_score)
                VALUES (%s, 'v1.0.0-test', 0, 0.30, 0.10);
            """, (reading_id,))


def test_fluxo_completo(conn):
    """Insere reading → alert → prediction e verifica via query JOIN."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        # INSERT reading
        cur.execute("""
            INSERT INTO sentinela_ambiental.sensor_readings
            (sensor_id, latitude, longitude, temperature_k, frp, satellite_type, confidence)
            VALUES (1, -99.123, -99.456, 999.0, 999.0, 0, 99) RETURNING id;
        """)
        rid = cur.fetchone()["id"]

        # INSERT alert
        cur.execute("""
            INSERT INTO sentinela_ambiental.alerts_history
            (reading_id, alert_type, severity, description)
            VALUES (%s, 'TEST', 'CRITICAL', 'teste_pipeline');
        """, (rid,))

        # INSERT prediction
        cur.execute("""
            INSERT INTO sentinela_ambiental.ai_predictions
            (reading_id, model_version, prediction_class, prediction_probability, urgency_score)
            VALUES (%s, 'test', 1, 0.99, 0.99);
        """, (rid,))

        # Verifica JOIN completo
        cur.execute("""
            SELECT sr.latitude, ah.severity, ap.prediction_class
            FROM sentinela_ambiental.sensor_readings sr
            JOIN sentinela_ambiental.alerts_history ah ON sr.id = ah.reading_id
            JOIN sentinela_ambiental.ai_predictions ap ON sr.id = ap.reading_id
            WHERE sr.id = %s;
        """, (rid,))
        row = cur.fetchone()
        assert row is not None
        assert float(row["latitude"]) == -99.123
        assert row["severity"] == "CRITICAL"
        assert row["prediction_class"] == 1
