-- ================================================
-- TETRA Monitor — Schema PostgreSQL
-- Ejecutar via setup.sh (lee credenciales del .env)
-- ================================================

-- Tabla de eventos
CREATE TABLE IF NOT EXISTS eventos (
    id          SERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    grupo       INTEGER NOT NULL,
    ssi         INTEGER NOT NULL,
    texto       TEXT,
    ruta_audio  TEXT
);

CREATE INDEX IF NOT EXISTS idx_eventos_timestamp ON eventos (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_eventos_grupo     ON eventos (grupo);
CREATE INDEX IF NOT EXISTS idx_eventos_ssi       ON eventos (ssi);

-- Conceder acceso a tablas y secuencias al usuario de la app
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tetra;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tetra;

-- Privilegios por defecto para objetos futuros
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON TABLES TO tetra;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON SEQUENCES TO tetra;