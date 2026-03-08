import os
import time
from core.logger import logger

# Cada cuántos segundos se ejecuta la limpieza
CLEANUP_INTERVAL = 3600  # 1 hora

class AudioCleanup:
    def __init__(self, output_dir: str, retention_days: int):
        self.output_dir = output_dir
        self.retention_seconds = retention_days * 86400
        self._last_cleanup = 0.0
        logger.info(
            f"[AudioCleanup] Retención configurada a {retention_days} días "
            f"— limpieza cada {CLEANUP_INTERVAL // 3600}h"
        )

    def run_if_due(self):
        """Llamar desde el bucle principal — solo ejecuta si ha pasado CLEANUP_INTERVAL."""
        now = time.monotonic()
        if now - self._last_cleanup < CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        self._cleanup()

    def _cleanup(self):
        if not os.path.isdir(self.output_dir):
            logger.warning(f"[AudioCleanup] Directorio no encontrado: {self.output_dir}")
            return

        cutoff = time.time() - self.retention_seconds
        deleted = 0
        errors = 0

        for filename in os.listdir(self.output_dir):
            if not filename.endswith(".flac"):
                continue
            filepath = os.path.join(self.output_dir, filename)
            try:
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    logger.debug(f"[AudioCleanup] Eliminado: {filename}")
                    deleted += 1
            except Exception as e:
                logger.error(f"[AudioCleanup] Error eliminando {filename}: {e}")
                errors += 1

        if deleted or errors:
            logger.info(f"[AudioCleanup] Limpieza completada — eliminados: {deleted}, errores: {errors}")
        else:
            logger.debug("[AudioCleanup] Limpieza completada — ningún fichero expirado")