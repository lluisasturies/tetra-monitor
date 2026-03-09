-- ================================================
-- TETRA Monitor — Schema PostgreSQL
-- Ejecutar via setup.sh (lee credenciales del .env)
-- @@DB_USER@@ se sustituye por el valor de DB_USER en .env
-- ================================================

-- Tabla de llamadas (solo las que disparan una keyword)
CREATE TABLE IF NOT EXISTS llamadas (
    id          SERIAL PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    grupo       INTEGER NOT NULL,
    ssi         INTEGER NOT NULL,
    texto       TEXT,
    ruta_audio  TEXT
);

CREATE INDEX IF NOT EXISTS idx_llamadas_timestamp ON llamadas (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_llamadas_grupo     ON llamadas (grupo);
CREATE INDEX IF NOT EXISTS idx_llamadas_ssi       ON llamadas (ssi);

-- Permisos
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO @@DB_USER@@;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO @@DB_USER@@;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON TABLES TO @@DB_USER@@;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON SEQUENCES TO @@DB_USER@@;
