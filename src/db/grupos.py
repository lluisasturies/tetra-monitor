from pathlib import Path
from psycopg2.extras import RealDictCursor
from core.logger import logger
from db.pool import DBPool

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


class GruposDB:
    def __init__(self, pool: DBPool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Semilla inicial desde YAML
    # ------------------------------------------------------------------

    def seed_from_yaml(self, filepath: str | Path) -> bool:
        """
        Carga grupos, carpetas y scan lists desde un YAML si las tablas están vacías.
        El orden de carpetas y de grupos dentro de cada carpeta se asigna
        automáticamente por posición en el YAML (0, 1, 2...) si no se especifica.
        Devuelve True si se insertaron datos, False si ya había datos o hubo error.
        """
        if yaml is None:
            logger.error("[GruposDB] PyYAML no disponible, no se puede cargar la semilla")
            return False

        filepath = Path(filepath)
        if not filepath.exists():
            logger.warning(f"[GruposDB] No existe el fichero de semilla: {filepath}")
            return False

        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM grupos")
                count = cur.fetchone()[0]
            conn.rollback()

            if count > 0:
                logger.info("[GruposDB] La tabla grupos ya tiene datos, semilla omitida")
                return False

            with open(filepath, "r") as f:
                data = yaml.safe_load(f) or {}

            grupos     = data.get("grupos", [])
            carpetas   = data.get("carpetas", [])
            scan_lists = data.get("scan_lists", [])

            conn.autocommit = False
            with conn.cursor() as cur:
                # Grupos
                for g in grupos:
                    cur.execute(
                        """
                        INSERT INTO grupos (gssi, nombre)
                        VALUES (%s, %s)
                        ON CONFLICT (gssi) DO NOTHING
                        """,
                        (g["gssi"], g["nombre"])
                    )

                # Carpetas — orden por posición si no se especifica
                for carpeta_orden, c in enumerate(carpetas):
                    orden_carpeta = c.get("orden", carpeta_orden)
                    cur.execute(
                        """
                        INSERT INTO carpetas (nombre, orden)
                        VALUES (%s, %s)
                        ON CONFLICT (nombre) DO NOTHING
                        RETURNING id
                        """,
                        (c["nombre"], orden_carpeta)
                    )
                    row = cur.fetchone()
                    if row is None:
                        cur.execute("SELECT id FROM carpetas WHERE nombre = %s", (c["nombre"],))
                        row = cur.fetchone()
                    carpeta_id = row[0]

                    # Grupos dentro de la carpeta — orden por posición si no se especifica
                    # Acepta tanto lista de ints [36001, 36002] como lista de dicts [{gssi: 36001}, ...]
                    for grupo_orden, entry in enumerate(c.get("grupos", [])):
                        if isinstance(entry, int):
                            gssi        = entry
                            orden_grupo = grupo_orden
                        else:
                            gssi        = entry["gssi"]
                            orden_grupo = entry.get("orden", grupo_orden)
                        cur.execute(
                            """
                            INSERT INTO carpeta_grupos (carpeta_id, gssi, orden)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (carpeta_id, gssi, orden_grupo)
                        )

                # Scan lists
                for sl in scan_lists:
                    cur.execute(
                        """
                        INSERT INTO scan_lists (nombre)
                        VALUES (%s)
                        ON CONFLICT (nombre) DO NOTHING
                        RETURNING id
                        """,
                        (sl["nombre"],)
                    )
                    row = cur.fetchone()
                    if row is None:
                        cur.execute("SELECT id FROM scan_lists WHERE nombre = %s", (sl["nombre"],))
                        row = cur.fetchone()
                    sl_id = row[0]

                    for gssi in sl.get("grupos", []):
                        cur.execute(
                            """
                            INSERT INTO scan_list_grupos (scan_list_id, gssi)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (sl_id, gssi)
                        )

            conn.commit()
            logger.info(
                f"[GruposDB] Semilla cargada: {len(grupos)} grupos, "
                f"{len(carpetas)} carpetas, {len(scan_lists)} scan lists"
            )
            return True

        except Exception as e:
            conn.rollback()
            import traceback
            logger.error(f"[GruposDB] Error cargando semilla: {e}\n{traceback.format_exc()}")
            return False
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Grupos
    # ------------------------------------------------------------------

    def get_nombre(self, gssi: int) -> str:
        """Devuelve el nombre del grupo para un GSSI, o el propio GSSI como string si no existe."""
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT nombre FROM grupos WHERE gssi = %s", (gssi,))
                row = cur.fetchone()
                return row[0] if row else str(gssi)
        except Exception as e:
            logger.error(f"[GruposDB] Error obteniendo nombre para gssi={gssi}: {e}")
            return str(gssi)
        finally:
            conn.rollback()
            self.pool.putconn(conn)

    def listar(self, solo_activos: bool = True) -> list[dict]:
        """Devuelve todos los grupos, opcionalmente solo los activos."""
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if solo_activos:
                    cur.execute("SELECT gssi, nombre, activo FROM grupos WHERE activo = TRUE ORDER BY gssi")
                else:
                    cur.execute("SELECT gssi, nombre, activo FROM grupos ORDER BY gssi")
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"[GruposDB] Error listando grupos: {e}")
            return []
        finally:
            conn.rollback()
            self.pool.putconn(conn)

    def upsert_grupo(self, gssi: int, nombre: str, activo: bool = True) -> bool:
        """Inserta o actualiza un grupo."""
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO grupos (gssi, nombre, activo)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (gssi) DO UPDATE
                        SET nombre = EXCLUDED.nombre,
                            activo = EXCLUDED.activo
                    """,
                    (gssi, nombre, activo)
                )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"[GruposDB] Error en upsert_grupo gssi={gssi}: {e}")
            return False
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Carpetas
    # ------------------------------------------------------------------

    def listar_carpetas(self) -> list[dict]:
        """
        Devuelve todas las carpetas con sus grupos anidados.
        Formato: [{id, nombre, orden, grupos: [{gssi, nombre, orden}, ...]}, ...]
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        c.id,
                        c.nombre   AS carpeta_nombre,
                        c.orden    AS carpeta_orden,
                        g.gssi,
                        g.nombre   AS grupo_nombre,
                        cg.orden   AS grupo_orden
                    FROM carpetas c
                    LEFT JOIN carpeta_grupos cg ON cg.carpeta_id = c.id
                    LEFT JOIN grupos g          ON g.gssi = cg.gssi
                    ORDER BY c.orden, c.nombre, cg.orden, g.gssi
                """)
                rows = cur.fetchall()

            result: dict[int, dict] = {}
            for r in rows:
                c_id = r["id"]
                if c_id not in result:
                    result[c_id] = {
                        "id":     c_id,
                        "nombre": r["carpeta_nombre"],
                        "orden":  r["carpeta_orden"],
                        "grupos": [],
                    }
                if r["gssi"] is not None:
                    result[c_id]["grupos"].append({
                        "gssi":   r["gssi"],
                        "nombre": r["grupo_nombre"],
                        "orden":  r["grupo_orden"],
                    })
            return list(result.values())

        except Exception as e:
            logger.error(f"[GruposDB] Error listando carpetas: {e}")
            return []
        finally:
            conn.rollback()
            self.pool.putconn(conn)

    def upsert_carpeta(self, nombre: str, orden: int = 0) -> int | None:
        """Inserta o actualiza una carpeta. Devuelve el id, o None si hubo error."""
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO carpetas (nombre, orden)
                    VALUES (%s, %s)
                    ON CONFLICT (nombre) DO UPDATE
                        SET orden = EXCLUDED.orden
                    RETURNING id
                    """,
                    (nombre, orden)
                )
                carpeta_id = cur.fetchone()[0]
            conn.commit()
            return carpeta_id
        except Exception as e:
            conn.rollback()
            logger.error(f"[GruposDB] Error en upsert_carpeta '{nombre}': {e}")
            return None
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    def set_grupos_carpeta(self, carpeta_id: int, gssi_orden: list[dict]) -> bool:
        """
        Reemplaza completamente los grupos de una carpeta.
        gssi_orden: [{gssi: int, orden: int}, ...]
        """
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("DELETE FROM carpeta_grupos WHERE carpeta_id = %s", (carpeta_id,))
                for entry in gssi_orden:
                    cur.execute(
                        """
                        INSERT INTO carpeta_grupos (carpeta_id, gssi, orden)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (carpeta_id, entry["gssi"], entry.get("orden", 0))
                    )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"[GruposDB] Error actualizando grupos de carpeta {carpeta_id}: {e}")
            return False
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    def borrar_carpeta(self, carpeta_id: int) -> bool:
        """Elimina una carpeta (los grupos NO se eliminan, solo la relación)."""
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute("DELETE FROM carpetas WHERE id = %s", (carpeta_id,))
                deleted = cur.rowcount
            conn.commit()
            return deleted > 0
        except Exception as e:
            conn.rollback()
            logger.error(f"[GruposDB] Error borrando carpeta {carpeta_id}: {e}")
            return False
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Scan lists
    # ------------------------------------------------------------------

    def listar_scan_lists(self) -> list[dict]:
        """
        Devuelve las scan lists con sus grupos anidados.
        Formato: [{id, nombre, grupos: [{gssi, nombre, prioridad}, ...]}, ...]
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        sl.id,
                        sl.nombre AS scan_list,
                        g.gssi,
                        g.nombre  AS grupo_nombre,
                        slg.prioridad
                    FROM scan_lists sl
                    LEFT JOIN scan_list_grupos slg ON slg.scan_list_id = sl.id
                    LEFT JOIN grupos g             ON g.gssi = slg.gssi
                    ORDER BY sl.nombre, slg.prioridad DESC, g.gssi
                """)
                rows = cur.fetchall()

            result: dict[int, dict] = {}
            for r in rows:
                sl_id = r["id"]
                if sl_id not in result:
                    result[sl_id] = {"id": sl_id, "nombre": r["scan_list"], "grupos": []}
                if r["gssi"] is not None:
                    result[sl_id]["grupos"].append({
                        "gssi":      r["gssi"],
                        "nombre":    r["grupo_nombre"],
                        "prioridad": r["prioridad"],
                    })
            return list(result.values())

        except Exception as e:
            logger.error(f"[GruposDB] Error listando scan lists: {e}")
            return []
        finally:
            conn.rollback()
            self.pool.putconn(conn)
