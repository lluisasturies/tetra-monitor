import time
from psycopg2.pool import ThreadedConnectionPool
from psycopg2 import OperationalError
from core.logger import logger

POOL_MIN_CONN = 1
POOL_MAX_CONN = 5

# Numero de reintentos con backoff antes de cerrar el pool y reconectar
_GETCONN_RETRIES = 3
_GETCONN_RETRY_DELAY = 0.5  # segundos


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
                logger.info(
                    f"Pool de conexiones PostgreSQL iniciado "
                    f"(min={POOL_MIN_CONN}, max={POOL_MAX_CONN})"
                )
                return
            except OperationalError:
                wait = 2 ** i
                logger.warning(f"BD no disponible, reintentando en {wait}s...")
                time.sleep(wait)
        raise RuntimeError("No se pudo conectar a PostgreSQL tras varios intentos")

    def getconn(self):
        # Primer intento con backoff para absorber picos de carga
        # (pool temporalmente exhausto) sin destruir conexiones activas.
        for intento in range(_GETCONN_RETRIES):
            try:
                return self.pool.getconn()
            except Exception as e:
                if intento < _GETCONN_RETRIES - 1:
                    logger.warning(
                        f"Pool ocupado (intento {intento + 1}/{_GETCONN_RETRIES}): {e} "
                        f"-- reintentando en {_GETCONN_RETRY_DELAY}s"
                    )
                    time.sleep(_GETCONN_RETRY_DELAY)
                else:
                    # Ultimo recurso: cerrar y reconectar
                    logger.warning(f"Pool no disponible tras {_GETCONN_RETRIES} intentos ({e}), reconectando...")
                    try:
                        if self.pool:
                            self.pool.closeall()
                    except Exception:
                        pass
                    self._connect()
                    return self.pool.getconn()

    def putconn(self, conn):
        self.pool.putconn(conn)

    def closeall(self):
        if self.pool:
            self.pool.closeall()
            logger.info("Pool de conexiones PostgreSQL cerrado")
