from datetime import datetime
from psycopg2.extras import RealDictCursor
from core.logger import logger
from db.pool import DBPool


class LlamadasDB:
    def __init__(self, pool: DBPool):
        self.pool = pool

    def guardar(self, grupo: int, ssi: int, texto: str, ruta_audio: str | None) -> bool:
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO llamadas (timestamp, grupo, ssi, texto, ruta_audio)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (datetime.now(), grupo, ssi, texto, ruta_audio))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Error guardando llamada: {e}")
            return False
        finally:
            self.pool.putconn(conn)

    def listar(self, limit: int = 100) -> list:
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    'SELECT * FROM llamadas ORDER BY timestamp DESC LIMIT %s',
                    (limit,)
                )
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error listando llamadas: {e}")
            return []
        finally:
            self.pool.putconn(conn)

    def obtener(self, llamada_id: int) -> dict | None:
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('SELECT * FROM llamadas WHERE id = %s', (llamada_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error obteniendo llamada {llamada_id}: {e}")
            return None
        finally:
            self.pool.putconn(conn)
