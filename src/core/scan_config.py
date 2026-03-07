import os
import yaml
from pathlib import Path
from core import logger

base_dir = os.path.dirname(os.path.abspath(__file__))
scan_path = os.path.join(base_dir, "../../config/scan.yaml")
SCAN_CONFIG_PATH = Path(scan_path)

try:
    with open(scan_path, "r") as f:
        cfg = yaml.safe_load(f)
    logger.info(f"Archivo de Scan cargado correctamente desde {scan_path}")
except FileNotFoundError:
    logger.critical(f"No se encontró el archivo de Scan: {scan_path}")
    raise
except yaml.YAMLError as e:
    logger.critical(f"Error parseando el archivo de Scan: {e}")
    raise

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
                logger.info(f"Configuración de Scan cargada: gssi='{self.gssi}', scan_list='{self.scan_list}'")
            except yaml.YAMLError as e:
                logger.error(f"Error leyendo Scan config: {e}")
                self.gssi = ""
                self.scan_list = ""
        else:
            logger.warning(f"No existe el archivo de Scan en {SCAN_CONFIG_PATH}, usando valores vacíos")
            self.gssi = ""
            self.scan_list = ""

    def save(self):
        try:
            with open(SCAN_CONFIG_PATH, "w") as f:
                yaml.safe_dump({
                    "gssi": self.gssi,
                    "scan_list": self.scan_list
                }, f)
            logger.info(f"Configuración de Scan guardada correctamente en {SCAN_CONFIG_PATH}")
        except Exception as e:
            logger.error(f"No se pudo guardar la configuración de Scan: {e}")

    def update_gssi(self, gssi: str):
        logger.info(f"Actualizando GSSI a: {gssi}")
        self.gssi = gssi
        self.save()

    def update_scan_list(self, scan_list: str = ""):
        logger.info(f"Actualizando a Scan List: {scan_list}")
        self.scan_list = scan_list
        self.save()

scan_config = ScanConfig()