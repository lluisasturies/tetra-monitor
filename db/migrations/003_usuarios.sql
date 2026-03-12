-- Migracion 003: sistema de usuarios con roles y refresh tokens persistentes
-- Ejecutar: psql -U <user> -d <dbname> -f db/migrations/003_usuarios.sql

BEGIN;

-- -------------------------------------------------------------------------
-- Tabla de usuarios
-- Roles disponibles:
--   admin    -> acceso total: lectura + escritura + gestion de usuarios
--   operator -> puede modificar afiliacion, keywords y grupos
--   viewer   -> solo lectura (llamadas, grupos, estado, health)
-- -------------------------------------------------------------------------
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

COMMENT ON TABLE  usuarios              IS 'Usuarios de la API REST';
COMMENT ON COLUMN usuarios.rol          IS 'admin | operator | viewer';
COMMENT ON COLUMN usuarios.password_hash IS 'Hash bcrypt de la contrasena';

-- -------------------------------------------------------------------------
-- Tabla de refresh tokens (persistentes, sobreviven reinicios del proceso)
-- -------------------------------------------------------------------------
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

COMMIT;
