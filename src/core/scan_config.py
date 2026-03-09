import yaml
from pathlib import Path
from core.logger import logger


class ScanConfig:
    def __init__(self, filepath: str | Path):
        self._filepath = Path(filepath)
        self.gssi: str = ""
        self.scan_list: str = ""
        self._last_mtime: float = 0.0
        self._load()

    def _load(self):
        if self._filepath.exists():
            try:
                with open(self._filepath, "r") as f:
                    data = yaml.safe_load(f) or {}
                scan = data.get("scan", {})
                self.gssi = scan.get("gssi", "")
                self.scan_list = scan.get("scan_list", "")
                self._last_mtime = self._filepath.stat().st_mtime
                logger.info("Scan config cargada correctamente")
            except yaml.YAMLError as e:
                logger.error(f"Error leyendo scan config: {e}")
                self.gssi = ""
                self.scan_list = ""
        else:
            logger.warning(f"No existe scan.yaml en {self._filepath}, usando valores vacíos")

    def reload_if_changed(self) -> bool:
        """Relee desde disco si el fichero fue modificado. Devuelve True si hubo cambios."""
        if not self._filepath.exists():
            return False
        try:
            mtime = self._filepath.stat().st_mtime
        except OSError:
            return False
        if mtime <= self._last_mtime:
            return False
        prev_gssi = self.gssi
        prev_scan_list = self.scan_list
        self._load()
        changed = (self.gssi != prev_gssi) or (self.scan_list != prev_scan_list)
        if changed:
            logger.info(
                f"[ScanConfig] Cambio detectado — gssi: '{prev_gssi}'->'{self.gssi}', "
                f"scan_list: '{prev_scan_list}'->'{self.scan_list}'"
            )
        return changed

    def save(self):
        try:
            with open(self._filepath, "w") as f:
                yaml.safe_dump({"scan": {"gssi": self.gssi, "scan_list": self.scan_list}}, f)
            self._last_mtime = self._filepath.stat().st_mtime
            logger.info(f"Scan config guardada en {self._filepath}")
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
