from datetime import datetime
from psycopg2.extras import RealDictCursor
from core.logger import logger
from db.pool import DBPool

_BASE_SELECT = """
    SELECT l.*, g.nombre AS grupo_nombre
    FROM llamadas l
    LEFT JOIN grupos g ON g.gssi = l.grupo
"""


class LlamadasDB:
    def __init__(self, pool: DBPool):
        self.pool = pool

    def guardar(self, grupo: int, ssi: int, texto: str, ruta_audio: str | None) -> bool:
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO llamadas (timestamp, grupo, ssi, texto, ruta_audio)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (datetime.now(), grupo, ssi, texto, ruta_audio),
                )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error guardando llamada: {e}")
            return False
        finally:
            self.pool.putconn(conn)

    def listar(self, limit: int = 100) -> list:
        """Listado simple sin filtros (compatibilidad interna)."""
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    _BASE_SELECT + "ORDER BY l.timestamp DESC LIMIT %s",
                    (limit,),
                )
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error listando llamadas: {e}")
            return []
        finally:
            self.pool.putconn(conn)

    def listar_filtrado(
        self,
        limit: int = 50,
        offset: int = 0,
        gssi: int | None = None,
        ssi: int | None = None,
        texto: str | None = None,
    ) -> tuple[list, int]:
        """
        Listado con paginación y filtros opcionales.
        Devuelve (filas, total) donde total es el número de resultados sin paginar.
        Usa SQL parametrizado para todas las condiciones del WHERE.
        """
        conditions: list[str] = []
        params: list = []

        if gssi is not None:
            conditions.append("l.grupo = %s")
            params.append(gssi)
        if ssi is not None:
            conditions.append("l.ssi = %s")
            params.append(ssi)
        if texto:
            conditions.append("l.texto ILIKE %s")
            params.append(f"%{texto}%")

        # La cláusula WHERE se construye solo con literales hardcodeados (%s),
        # nunca con valores de usuario interpolados directamente en el string SQL.
        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM llamadas l {where_clause}",  # noqa: S608
                    params,
                )
                total = cur.fetchone()["count"]

                cur.execute(
                    f"{_BASE_SELECT} {where_clause} ORDER BY l.timestamp DESC LIMIT %s OFFSET %s",  # noqa: S608
                    params + [limit, offset],
                )
                rows = cur.fetchall()
            return rows, total
        except Exception as e:
            logger.error(f"Error en listar_filtrado: {e}")
            return [], 0
        finally:
            self.pool.putconn(conn)

    def obtener(self, llamada_id: int) -> dict | None:
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    _BASE_SELECT + "WHERE l.id = %s",
                    (llamada_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error obteniendo llamada {llamada_id}: {e}")
            return None
        finally:
            self.pool.putconn(conn)
