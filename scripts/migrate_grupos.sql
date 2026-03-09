-- Migración: catálogo de grupos TETRA y listas de escaneo
-- Ejecutar una sola vez sobre la BD existente.

CREATE TABLE IF NOT EXISTS grupos (
    gssi        INTEGER PRIMARY KEY,
    nombre      TEXT    NOT NULL,
    descripcion TEXT,
    activo      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS scan_lists (
    id     SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);

-- Relación N:M: un GSSI puede estar en varias listas y una lista contiene varios GSSIs.
CREATE TABLE IF NOT EXISTS scan_list_grupos (
    scan_list_id INTEGER  REFERENCES scan_lists(id) ON DELETE CASCADE,
    gssi         INTEGER  REFERENCES grupos(gssi)   ON DELETE CASCADE,
    prioridad    SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (scan_list_id, gssi)
);
