-- Migration: Adiciona tabela de predições da IA
-- Executar manualmente se o banco já existir (sem rebuild):
--   psql -U postgres -d postgres -h localhost -p 5436 -f db/migrations/add_ai_predictions.sql

CREATE TABLE IF NOT EXISTS sentinela_ambiental.ai_predictions (
    id SERIAL PRIMARY KEY,
    reading_id INT REFERENCES sentinela_ambiental.sensor_readings(id),
    model_version VARCHAR(50) NOT NULL,
    prediction_class INT NOT NULL,
    prediction_probability DOUBLE PRECISION NOT NULL,
    urgency_score DOUBLE PRECISION,
    predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_predictions_reading_id ON sentinela_ambiental.ai_predictions(reading_id);
CREATE INDEX IF NOT EXISTS idx_ai_predictions_predicted_at ON sentinela_ambiental.ai_predictions(predicted_at);
