-- Este fichero ya no es necesario.
-- Las tablas grupos, scan_lists y scan_list_grupos están incluidas
-- en data/db/schema.sql y se crean automáticamente con setup.sh.
--
-- Para instalar en una BD existente (sin reinstalar desde cero):
--
--   psql -U $DB_USER -d tetra -f scripts/migrate_grupos.sql
--

CREATE TABLE IF NOT EXISTS grupos (
    gssi        INTEGER PRIMARY KEY,
    nombre      TEXT    NOT NULL,
    descripcion TEXT,
    activo      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_grupos_activo ON grupos (activo);

CREATE TABLE IF NOT EXISTS scan_lists (
    id     SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS scan_list_grupos (
    scan_list_id INTEGER  REFERENCES scan_lists(id) ON DELETE CASCADE,
    gssi         INTEGER  REFERENCES grupos(gssi)   ON DELETE CASCADE,
    prioridad    SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (scan_list_id, gssi)
);
