from datetime import datetime
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from core.logger import logger
from db.pool import DBPool

_BASE_SELECT = sql.SQL("""
    SELECT l.*, g.nombre AS grupo_nombre
    FROM llamadas l
    LEFT JOIN grupos g ON g.gssi = l.grupo
""")

_COUNT_SELECT = sql.SQL("SELECT COUNT(*) FROM llamadas l")


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
            conn.autocommit = True
            self.pool.putconn(conn)

    def listar(self, limit: int = 100) -> list:
        """Listado simple sin filtros (compatibilidad interna)."""
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    _BASE_SELECT + sql.SQL("ORDER BY l.timestamp DESC LIMIT %s"),
                    (limit,),
                )
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error listando llamadas: {e}")
            return []
        finally:
            # FIX: rollback antes de devolver la conexion al pool para
            # que no quede en estado sucio si hubo un error en la query.
            conn.rollback()
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
        Listado con paginacion y filtros opcionales.
        Devuelve (filas, total) donde total es el numero de resultados sin paginar.
        La query se compone con psycopg2.sql para evitar cualquier interpolacion directa.
        """
        clauses: list[sql.Composable] = []
        params: list = []

        if gssi is not None:
            clauses.append(sql.SQL("l.grupo = %s"))
            params.append(gssi)
        if ssi is not None:
            clauses.append(sql.SQL("l.ssi = %s"))
            params.append(ssi)
        if texto:
            clauses.append(sql.SQL("l.texto ILIKE %s"))
            params.append(f"%{texto}%")

        where = (
            sql.SQL(" WHERE ") + sql.SQL(" AND ").join(clauses)
            if clauses
            else sql.SQL("")
        )

        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(_COUNT_SELECT + where, params)
                total = cur.fetchone()["count"]

                cur.execute(
                    _BASE_SELECT + where + sql.SQL(" ORDER BY l.timestamp DESC LIMIT %s OFFSET %s"),
                    params + [limit, offset],
                )
                rows = cur.fetchall()
            return rows, total
        except Exception as e:
            logger.error(f"Error en listar_filtrado: {e}")
            return [], 0
        finally:
            conn.rollback()
            self.pool.putconn(conn)

    def obtener(self, llamada_id: int) -> dict | None:
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    _BASE_SELECT + sql.SQL("WHERE l.id = %s"),
                    (llamada_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error obteniendo llamada {llamada_id}: {e}")
            return None
        finally:
            conn.rollback()
            self.pool.putconn(conn)
