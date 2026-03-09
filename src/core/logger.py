import os
import logging
from logging.handlers import RotatingFileHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR  = os.path.join(BASE_DIR, "../../logs")
os.makedirs(LOG_DIR, exist_ok=True)


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


def _setup_logger():
    formatter         = logging.Formatter("%(asctime)s | [%(levelname)s] | %(message)s")
    console_formatter = ColorFormatter("%(asctime)s | [%(levelname)s] | %(message)s")

    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)  # nivel por defecto, main.py lo ajusta tras leer config
    app_logger.propagate = False

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    app_logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "tetra_monitor.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    app_logger.addHandler(file_handler)

    calls_logger = logging.getLogger("calls")
    calls_logger.setLevel(logging.INFO)
    calls_logger.propagate = False

    calls_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "calls.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=10
    )
    calls_handler.setFormatter(formatter)
    calls_logger.addHandler(calls_handler)

    return app_logger, calls_logger


def set_level(level_name: str):
    """Ajusta el nivel de log en todos los loggers. Llamar desde main.py tras leer config."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.getLogger("app").setLevel(level)
    logging.getLogger("calls").setLevel(level)


logger, calls_logger = _setup_logger()
