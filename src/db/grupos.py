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
        Carga grupos y scan lists desde un YAML si las tablas están vacías.
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
            # Comprobación de tabla vacía (lectura simple, sin transacción explícita)
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM grupos")
                count = cur.fetchone()[0]
            conn.rollback()  # cerrar la transacción implícita antes de cambiar autocommit

            if count > 0:
                logger.info("[GruposDB] La tabla grupos ya tiene datos, semilla omitida")
                return False

            with open(filepath, "r") as f:
                data = yaml.safe_load(f) or {}

            grupos     = data.get("grupos", [])
            scan_lists = data.get("scan_lists", [])

            # Ahora sí podemos cambiar autocommit (no hay transacción abierta)
            conn.autocommit = False
            with conn.cursor() as cur:
                for g in grupos:
                    cur.execute(
                        """
                        INSERT INTO grupos (gssi, nombre, descripcion)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (gssi) DO NOTHING
                        """,
                        (g["gssi"], g["nombre"], g.get("descripcion"))
                    )

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
            logger.info(f"[GruposDB] Semilla cargada: {len(grupos)} grupos, {len(scan_lists)} scan lists")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"[GruposDB] Error cargando semilla: {e}")
            return False
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Consultas
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
                    cur.execute("SELECT * FROM grupos WHERE activo = TRUE ORDER BY gssi")
                else:
                    cur.execute("SELECT * FROM grupos ORDER BY gssi")
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"[GruposDB] Error listando grupos: {e}")
            return []
        finally:
            conn.rollback()
            self.pool.putconn(conn)

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
                        g.nombre AS grupo_nombre,
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

    # ------------------------------------------------------------------
    # Escritura
    # ------------------------------------------------------------------

    def upsert_grupo(self, gssi: int, nombre: str, descripcion: str | None = None, activo: bool = True) -> bool:
        """Inserta o actualiza un grupo."""
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO grupos (gssi, nombre, descripcion, activo)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (gssi) DO UPDATE
                        SET nombre      = EXCLUDED.nombre,
                            descripcion = EXCLUDED.descripcion,
                            activo      = EXCLUDED.activo
                    """,
                    (gssi, nombre, descripcion, activo)
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
