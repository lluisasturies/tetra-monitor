-- Crear tabla eventos
CREATE TABLE IF NOT EXISTS eventos (
    id          SERIAL PRIMARY KEY,
    timestamp   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    grupo       INTEGER NOT NULL,
    ssi         INTEGER NOT NULL,
    texto       TEXT NOT NULL,
    ruta_audio  TEXT,
    -- Columna generada para búsqueda full-text en español
    texto_ts    tsvector GENERATED ALWAYS AS (to_tsvector('spanish', texto)) STORED
);

-- Índices para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_eventos_grupo     ON eventos(grupo);
CREATE INDEX IF NOT EXISTS idx_eventos_ssi       ON eventos(ssi);
CREATE INDEX IF NOT EXISTS idx_eventos_timestamp ON eventos(timestamp);
-- Índice GIN para búsqueda full-text
CREATE INDEX IF NOT EXISTS idx_eventos_texto     ON eventos USING GIN(texto_ts);
