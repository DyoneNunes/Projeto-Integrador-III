-- =============================================================================
-- SQL ANALYTICS - SENTINELA AMBIENTAL
-- Views para Ciência de Dados e Mitigação de Viés
-- =============================================================================

-- 1. View de Agrupamento Regional (Simulação de Municípios por proximidade)
-- Útil para identificar clusters de fogo sem precisar de shapefiles complexos inicialmente.
CREATE OR REPLACE VIEW sentinela_ambiental.vw_foci_by_region AS
SELECT 
    ROUND(latitude::numeric, 1) as reg_lat,
    ROUND(longitude::numeric, 1) as reg_lon,
    COUNT(*) as total_readings,
    COUNT(*) FILTER (WHERE satellite_type = 0) as presumed_wildfire,
    COUNT(*) FILTER (WHERE satellite_type != 0) as static_sources,
    AVG(temperature_k) as avg_temp,
    MAX(frp) as max_frp,
    CURRENT_DATE as analysis_date
FROM sentinela_ambiental.sensor_readings
WHERE reading_timestamp > CURRENT_TIMESTAMP - INTERVAL '24 hours'
GROUP BY 1, 2
ORDER BY presumed_wildfire DESC;

-- 2. View de Tendência de Intensidade (Média Móvel de FRP)
-- Ajuda a identificar se o fogo está ficando mais intenso ou perdendo força.
CREATE OR REPLACE VIEW sentinela_ambiental.vw_frp_intensity_trend AS
WITH daily_stats AS (
    SELECT 
        reading_timestamp::date as day,
        AVG(frp) as avg_frp,
        COUNT(*) as foci_count
    FROM sentinela_ambiental.sensor_readings
    WHERE satellite_type = 0 -- Apenas fogo real
    GROUP BY 1
)
SELECT 
    day,
    foci_count,
    avg_frp,
    AVG(avg_frp) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) as moving_avg_7d_frp
FROM daily_stats
ORDER BY day DESC;

-- 3. View de Monitoramento de Viés (Distribuição por Tipo de Satélite)
CREATE OR REPLACE VIEW sentinela_ambiental.vw_bias_monitor AS
SELECT 
    satellite_type,
    CASE 
        WHEN satellite_type = 0 THEN 'Presumed Wildfire'
        WHEN satellite_type = 1 THEN 'Active Volcano'
        WHEN satellite_type = 2 THEN 'Other Static Source'
        WHEN satellite_type = 3 THEN 'Offshore'
        ELSE 'Unknown'
    END as source_description,
    COUNT(*) as total_detections,
    AVG(confidence) as avg_confidence
FROM sentinela_ambiental.sensor_readings
GROUP BY 1, 2;
