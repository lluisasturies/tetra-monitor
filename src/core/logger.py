import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "../../logs"

class ColorFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        message = super().format(record)
        return f"{color}{message}{self.RESET}"


def setup_logger(debug=False):
    os.makedirs(LOG_DIR, exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_formatter = ColorFormatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(level)

    # -----------------------
    # Console
    # -----------------------
    console = logging.StreamHandler()
    console.setFormatter(console_formatter)

    # -----------------------
    # System log
    # -----------------------
    system_file = RotatingFileHandler(
        f"{LOG_DIR}/tetra_monitor.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10
    )
    system_file.setFormatter(formatter)

    # -----------------------
    # Call events log
    # -----------------------
    call_file = RotatingFileHandler(
        f"{LOG_DIR}/calls.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10
    )
    call_file.setFormatter(formatter)

    call_logger = logging.getLogger("calls")
    call_logger.setLevel(level)
    call_logger.addHandler(call_file)

    root.addHandler(console)
    root.addHandler(system_file)

    return logging.getLogger(__name__)