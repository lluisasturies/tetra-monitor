import os
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR  = os.path.join(BASE_DIR, "../../logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Valores por defecto — se sobreescriben con configure_rotation() desde main.py
_DEFAULT_MAX_BYTES    = 10 * 1024 * 1024  # 10 MB
_DEFAULT_BACKUP_COUNT = 10


class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


def _setup_logger(max_bytes: int = _DEFAULT_MAX_BYTES, backup_count: int = _DEFAULT_BACKUP_COUNT):
    formatter         = logging.Formatter("%(asctime)s | [%(levelname)s] | %(message)s")
    console_formatter = ColorFormatter("%(asctime)s | [%(levelname)s] | %(message)s")

    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False

    # Evitar duplicar handlers si se llama varias veces
    if not app_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        app_logger.addHandler(console_handler)

        file_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "tetra_monitor.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setFormatter(formatter)
        app_logger.addHandler(file_handler)

    calls_logger = logging.getLogger("calls")
    calls_logger.setLevel(logging.INFO)
    calls_logger.propagate = False

    if not calls_logger.handlers:
        calls_handler = RotatingFileHandler(
            os.path.join(LOG_DIR, "calls.log"),
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        calls_handler.setFormatter(formatter)
        calls_logger.addHandler(calls_handler)

    return app_logger, calls_logger


def configure_rotation(max_mb: int = 10, backup_count: int = 10):
    """
    Reconfigura el tamaño máximo y el número de backups de los ficheros de log.
    Llamar desde main.py tras leer config.yaml, antes del primer mensaje.

    Args:
        max_mb:       Tamaño máximo de cada fichero de log en MB (default: 10).
        backup_count: Número de ficheros de backup a conservar (default: 10).
    """
    max_bytes = max_mb * 1024 * 1024
    for logger_name in ("app", "calls"):
        lg = logging.getLogger(logger_name)
        for handler in lg.handlers:
            if isinstance(handler, RotatingFileHandler):
                handler.maxBytes    = max_bytes
                handler.backupCount = backup_count
    logging.getLogger("app").info(
        f"[logger] Rotación configurada: max={max_mb}MB, backups={backup_count}"
    )


def set_level(level_name: str):
    """Ajusta el nivel de log en todos los loggers. Llamar desde main.py tras leer config."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.getLogger("app").setLevel(level)
    logging.getLogger("calls").setLevel(level)


logger, calls_logger = _setup_logger()
