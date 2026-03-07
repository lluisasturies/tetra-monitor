import time
import psycopg2
from psycopg2 import OperationalError
from psycopg2.extras import RealDictCursor
from datetime import datetime
from core.logger import logger

class Database:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.conn = None
        self._connect()

    def _connect(self, retries=5):
        for i in range(retries):
            try:
                self.conn = psycopg2.connect(**self.kwargs)
                self.conn.autocommit = False
                return
            except OperationalError:
                wait = 2 ** i
                logger.warning(f"BD no disponible, reintentando en {wait}s...")
                time.sleep(wait)
        raise RuntimeError("No se pudo conectar a PostgreSQL")

    def _ensure_connection(self):
        try:
            with self.conn.cursor() as cur:  # cursor cerrado correctamente
                cur.execute("SELECT 1")
        except Exception:
            logger.warning("Conexión perdida, reconectando...")
            self._connect()

    def guardar_evento(self, grupo, ssi, texto, ruta_audio):
        self._ensure_connection()
        try:
            with self.conn.cursor() as cur:
                cur.execute('''
                    INSERT INTO eventos (timestamp, grupo, ssi, texto, ruta_audio)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (datetime.now(), grupo, ssi, texto, ruta_audio))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error guardando evento: {e}")

    def listar_eventos(self, limit=100):  # ← solo UNA definición
        self._ensure_connection()
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    'SELECT * FROM eventos ORDER BY timestamp DESC LIMIT %s',
                    (limit,)
                )
                return cur.fetchall()
        except Exception as e:
            logger.error(f"Error listando eventos: {e}")
            return []