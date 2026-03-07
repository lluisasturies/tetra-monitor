import os
import yaml
from pathlib import Path
from core.logger import logger

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCAN_CONFIG_PATH = Path(os.path.join(BASE_DIR, "../../config/scan.yaml"))


class ScanConfig:
    def __init__(self):
        self.gssi: str = ""
        self.scan_list: str = ""
        self._load()

    def _load(self):
        if SCAN_CONFIG_PATH.exists():
            try:
                with open(SCAN_CONFIG_PATH, "r") as f:
                    data = yaml.safe_load(f) or {}
                self.gssi = data.get("gssi", "")
                self.scan_list = data.get("scan_list", "")
                logger.info(f"Scan config cargada: gssi='{self.gssi}', scan_list='{self.scan_list}'")
            except yaml.YAMLError as e:
                logger.error(f"Error leyendo scan config: {e}")
                self.gssi = ""
                self.scan_list = ""
        else:
            logger.warning(f"No existe scan.yaml en {SCAN_CONFIG_PATH}, usando valores vacíos")

    def save(self):
        try:
            with open(SCAN_CONFIG_PATH, "w") as f:
                yaml.safe_dump({"gssi": self.gssi, "scan_list": self.scan_list}, f)
            logger.info(f"Scan config guardada en {SCAN_CONFIG_PATH}")
        except Exception as e:
            logger.error(f"No se pudo guardar scan config: {e}")

    def update_gssi(self, gssi: str):
        logger.info(f"Actualizando GSSI a: {gssi}")
        self.gssi = gssi
        self.save()

    def update_scan_list(self, scan_list: str = ""):
        logger.info(f"Actualizando scan list a: {scan_list}")
        self.scan_list = scan_list
        self.save()


scan_config = ScanConfig()
