import yaml
from pathlib import Path
from typing import List

SCAN_CONFIG_PATH = Path("config/scan.yaml")

class ScanConfig:
    def __init__(self):
        self.gssi: str = ""
        self.scan_list: List[int] = []
        self._load()

    def _load(self):
        if SCAN_CONFIG_PATH.exists():
            with open(SCAN_CONFIG_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
            self.gssi = data.get("gssi", "")
            self.scan_list = data.get("scan_list", [])
        else:
            self.gssi = ""
            self.scan_list = []

    def save(self):
        with open(SCAN_CONFIG_PATH, "w") as f:
            yaml.safe_dump({
                "gssi": self.gssi,
                "scan_list": self.scan_list
            }, f)

    def update_gssi(self, gssi: str):
        self.gssi = gssi
        self.save()

    def update_scan_list(self, scan_list: List[int]):
        self.scan_list = scan_list
        self.save()

scan_config = ScanConfig()