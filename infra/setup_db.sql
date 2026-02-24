-- 1. Limpieza total para asegurar integridad
DROP TABLE IF EXISTS btc_usdt;

-- 2. Crear la extensión
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 3. Crear la tabla con el tipo de dato recomendado (TIMESTAMPTZ)
CREATE TABLE btc_usdt (
    timestamp TIMESTAMPTZ NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume DOUBLE PRECISION
);

-- 4. Convertir en Hypertable
SELECT create_hypertable('btc_usdt', 'timestamp');

-- 5. Índice de alta velocidad
CREATE INDEX idx_btc_timestamp ON btc_usdt (timestamp DESC);