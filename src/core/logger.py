import os
import yaml
import logging
from logging.handlers import RotatingFileHandler

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../config/config.yaml")

try:
    with open(CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f) or {}
except Exception:
    cfg = {}

# Determinar nivel de logging
level_name = cfg.get("logging", {}).get("level", "INFO").upper()
level = getattr(logging, level_name, logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "../../logs")
os.makedirs(LOG_DIR, exist_ok=True)

class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",    # cyan
        "INFO": "\033[32m",     # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",    # red
        "CRITICAL": "\033[35m", # magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"

def setup_logger():
    # Logger principal (app)
    app_logger = logging.getLogger("app")
    app_logger.setLevel(level)
    app_logger.propagate = False  # evita duplicar mensajes

    formatter = logging.Formatter("%(asctime)s | [%(levelname)s] | %(message)s")
    console_formatter = ColorFormatter("%(asctime)s | [%(levelname)s] | %(message)s")

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    app_logger.addHandler(console_handler)

    # File handler
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "tetra_monitor.log"),
        maxBytes=10*1024*1024,
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    app_logger.addHandler(file_handler)

    # Logger para llamadas
    calls_logger = logging.getLogger("calls")
    calls_logger.setLevel(level)
    calls_logger.propagate = False

    calls_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "calls.log"),
        maxBytes=10*1024*1024,
        backupCount=10
    )
    calls_handler.setFormatter(formatter)
    calls_logger.addHandler(calls_handler)

    return app_logger, calls_logger

logger, calls_logger = setup_logger()