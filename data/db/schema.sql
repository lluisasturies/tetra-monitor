-- =============================================================================
-- TETRA Monitor — Schema completo de la base de datos
-- =============================================================================
-- Uso (instalacion limpia):
--   psql -U <db_user> -d tetra -f data/db/schema.sql
--
-- El script es idempotente: usa CREATE TABLE IF NOT EXISTS y
-- CREATE INDEX IF NOT EXISTS, por lo que puede ejecutarse de nuevo
-- sobre una BD existente sin causar errores.
--
-- El placeholder @@DB_USER@@ es reemplazado por scripts/setup.sh
-- con el valor de DB_USER definido en .env.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Grupos TETRA
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grupos (
    gssi    INTEGER      PRIMARY KEY,
    nombre  VARCHAR(128) NOT NULL,
    activo  BOOLEAN      NOT NULL DEFAULT TRUE
);

COMMENT ON TABLE  grupos        IS 'Grupos TETRA identificados por GSSI';
COMMENT ON COLUMN grupos.gssi   IS 'Group Short Subscriber Identity';
COMMENT ON COLUMN grupos.activo IS 'FALSE = grupo desactivado, no aparece en listados por defecto';

-- ---------------------------------------------------------------------------
-- Carpetas (agrupaciones visuales de grupos)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS carpetas (
    id     SERIAL       PRIMARY KEY,
    nombre VARCHAR(128) UNIQUE NOT NULL,
    orden  INTEGER      NOT NULL DEFAULT 0
);

COMMENT ON TABLE carpetas IS 'Agrupaciones visuales de grupos TETRA';

CREATE TABLE IF NOT EXISTS carpeta_grupos (
    carpeta_id INTEGER NOT NULL REFERENCES carpetas(id) ON DELETE CASCADE,
    gssi       INTEGER NOT NULL REFERENCES grupos(gssi) ON DELETE CASCADE,
    orden      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (carpeta_id, gssi)
);

CREATE INDEX IF NOT EXISTS idx_carpeta_grupos_gssi ON carpeta_grupos (gssi);

-- ---------------------------------------------------------------------------
-- Scan lists
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scan_lists (
    id     SERIAL       PRIMARY KEY,
    nombre VARCHAR(128) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_list_grupos (
    scan_list_id INTEGER NOT NULL REFERENCES scan_lists(id) ON DELETE CASCADE,
    gssi         INTEGER NOT NULL REFERENCES grupos(gssi)   ON DELETE CASCADE,
    prioridad    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (scan_list_id, gssi)
);

CREATE INDEX IF NOT EXISTS idx_scan_list_grupos_gssi ON scan_list_grupos (gssi);

-- ---------------------------------------------------------------------------
-- Llamadas registradas
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS llamadas (
    id          SERIAL       PRIMARY KEY,
    timestamp   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    grupo       INTEGER      REFERENCES grupos(gssi) ON DELETE SET NULL,
    ssi         INTEGER,
    texto       TEXT,
    ruta_audio  VARCHAR(512)
);

CREATE INDEX IF NOT EXISTS idx_llamadas_timestamp ON llamadas (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_llamadas_grupo     ON llamadas (grupo);

COMMENT ON TABLE  llamadas            IS 'Llamadas TETRA capturadas por el daemon PEI';
COMMENT ON COLUMN llamadas.grupo      IS 'GSSI del grupo de la llamada (puede ser NULL si el grupo fue eliminado)';
COMMENT ON COLUMN llamadas.ssi        IS 'SSI del terminal que inicia la llamada';
COMMENT ON COLUMN llamadas.texto      IS 'Transcripcion STT de la llamada';
COMMENT ON COLUMN llamadas.ruta_audio IS 'Ruta relativa al fichero FLAC grabado';

-- ---------------------------------------------------------------------------
-- Usuarios de la API REST
-- Roles:
--   admin    -> acceso total: lectura + escritura + gestion de usuarios
--   operator -> puede modificar afiliacion, keywords y grupos
--   viewer   -> solo lectura (llamadas, grupos, estado, health)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id            SERIAL       PRIMARY KEY,
    username      VARCHAR(64)  UNIQUE NOT NULL,
    email         VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    rol           VARCHAR(20)  NOT NULL DEFAULT 'viewer'
                               CHECK (rol IN ('admin', 'operator', 'viewer')),
    activo        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMPTZ
);

COMMENT ON TABLE  usuarios               IS 'Usuarios de la API REST';
COMMENT ON COLUMN usuarios.rol           IS 'admin | operator | viewer';
COMMENT ON COLUMN usuarios.password_hash IS 'Hash bcrypt de la contrasena';

-- ---------------------------------------------------------------------------
-- Refresh tokens JWT (persistentes, sobreviven reinicios del proceso)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          SERIAL       PRIMARY KEY,
    usuario_id  INTEGER      NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    token       VARCHAR(128) UNIQUE NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ  NOT NULL,
    revoked     BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token      ON refresh_tokens (token);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_usuario_id ON refresh_tokens (usuario_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens (expires_at);

COMMENT ON TABLE  refresh_tokens            IS 'Refresh tokens JWT persistentes';
COMMENT ON COLUMN refresh_tokens.expires_at IS 'El token es invalido despues de esta fecha aunque revoked=FALSE';

-- ---------------------------------------------------------------------------
-- Permisos
-- ---------------------------------------------------------------------------
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO @@DB_USER@@;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO @@DB_USER@@;
