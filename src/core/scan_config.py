import os
import yaml
from pathlib import Path
from typing import List

base_dir = os.path.dirname(os.path.abspath(__file__))
scan_path = os.path.join(base_dir, "../../config/scan.yaml")

try:
    with open(scan_path, "r") as f:
        cfg = yaml.safe_load(f)
except FileNotFoundError:
    raise FileNotFoundError(f"No se encontró el archivo de Scan: {scan_path}")
SCAN_CONFIG_PATH = Path(scan_path)

class ScanConfig:
    def __init__(self):
        self.gssi: str = ""
        self.scan_list: str = ""
        self._load()

    def _load(self):
        if SCAN_CONFIG_PATH.exists():
            with open(SCAN_CONFIG_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
            self.gssi = data.get("gssi", "")
            self.scan_list = data.get("scan_list", "")
        else:
            self.gssi = ""
            self.scan_list = ""

    def save(self):
        with open(SCAN_CONFIG_PATH, "w") as f:
            yaml.safe_dump({
                "gssi": self.gssi,
                "scan_list": self.scan_list
            }, f)

    def update_gssi(self, gssi: str):
        self.gssi = gssi
        self.save()

    def update_scan_list(self, scan_list: str = ""):
        self.scan_list = scan_list
        self.save()

scan_config = ScanConfig()