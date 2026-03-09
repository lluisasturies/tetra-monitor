-- ================================================
-- TETRA Monitor — Schema PostgreSQL
-- Ejecutar via setup.sh (lee credenciales del .env)
-- @@DB_USER@@ se sustituye por el valor de DB_USER en .env
-- ================================================

-- Tabla de llamadas
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

-- Catálogo de grupos TETRA (GSSI → nombre)
CREATE TABLE IF NOT EXISTS grupos (
    gssi        INTEGER PRIMARY KEY,
    nombre      TEXT    NOT NULL,
    activo      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_grupos_activo ON grupos (activo);

-- Carpetas organizativas (equivalente a las folders de la radio)
-- Un GSSI puede estar en varias carpetas
CREATE TABLE IF NOT EXISTS carpetas (
    id      SERIAL   PRIMARY KEY,
    nombre  TEXT     NOT NULL UNIQUE,
    orden   SMALLINT NOT NULL DEFAULT 0  -- orden de visualización
);

-- Relación N:M entre carpetas y grupos
CREATE TABLE IF NOT EXISTS carpeta_grupos (
    carpeta_id  INTEGER  REFERENCES carpetas(id)    ON DELETE CASCADE,
    gssi        INTEGER  REFERENCES grupos(gssi)    ON DELETE CASCADE,
    orden       SMALLINT NOT NULL DEFAULT 0,        -- orden dentro de la carpeta
    PRIMARY KEY (carpeta_id, gssi)
);

-- Listas de escaneo
CREATE TABLE IF NOT EXISTS scan_lists (
    id     SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

-- Relación N:M entre scan_lists y grupos
CREATE TABLE IF NOT EXISTS scan_list_grupos (
    scan_list_id INTEGER  REFERENCES scan_lists(id) ON DELETE CASCADE,
    gssi         INTEGER  REFERENCES grupos(gssi)   ON DELETE CASCADE,
    prioridad    SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (scan_list_id, gssi)
);

-- Permisos
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO @@DB_USER@@;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO @@DB_USER@@;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON TABLES TO @@DB_USER@@;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT ALL PRIVILEGES ON SEQUENCES TO @@DB_USER@@;
