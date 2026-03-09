import time
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2 import OperationalError
from core.logger import logger

POOL_MIN_CONN = 1
POOL_MAX_CONN = 5


class DBPool:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.pool: ThreadedConnectionPool | None = None
        self._connect(retries=5)

    def _connect(self, retries=5):
        for i in range(retries):
            try:
                self.pool = ThreadedConnectionPool(
                    POOL_MIN_CONN,
                    POOL_MAX_CONN,
                    **self.kwargs
                )
                logger.info(f"Pool de conexiones PostgreSQL iniciado (min={POOL_MIN_CONN}, max={POOL_MAX_CONN})")
                return
            except OperationalError:
                wait = 2 ** i
                logger.warning(f"BD no disponible, reintentando en {wait}s...")
                time.sleep(wait)
        raise RuntimeError("No se pudo conectar a PostgreSQL tras varios intentos")

    def getconn(self):
        try:
            return self.pool.getconn()
        except Exception:
            logger.warning("Pool no disponible, reconectando...")
            self._connect()
            return self.pool.getconn()

    def putconn(self, conn):
        self.pool.putconn(conn)

    def closeall(self):
        if self.pool:
            self.pool.closeall()
            logger.info("Pool de conexiones PostgreSQL cerrado")
