-- Crear tabla eventos
CREATE TABLE IF NOT EXISTS eventos (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    grupo INTEGER NOT NULL,
    ssi INTEGER NOT NULL,
    texto TEXT NOT NULL,
    ruta_audio TEXT
);

-- Índices opcionales para consultas rápidas
CREATE INDEX IF NOT EXISTS idx_eventos_grupo ON eventos(grupo);
CREATE INDEX IF NOT EXISTS idx_eventos_ssi ON eventos(ssi);
CREATE INDEX IF NOT EXISTS idx_eventos_timestamp ON eventos(timestamp);