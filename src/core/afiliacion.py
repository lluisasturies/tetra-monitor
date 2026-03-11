import re
import yaml
from pathlib import Path
from core.logger import logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from integrations.telegram_bot import TelegramBot

_RE_GSSI      = re.compile(r'^\d{1,8}$')
_RE_SCAN_LIST = re.compile(r'^[\w\-]{1,32}$')


class AfiliacionConfig:
    """
    Gestiona la afiliación activa del radio vía PEI:
    qué GSSI y scan list tiene programado el radio en este momento.

    scan_list es None cuando no hay lista de escaneo activa.
    No gestiona el catálogo de grupos — eso es responsabilidad de GruposDB.
    """

    def __init__(self, filepath: str | Path, bot: "TelegramBot | None" = None):
        self._filepath = Path(filepath)
        self._bot = bot
        self.gssi: str = ""
        self.scan_list: str | None = None
        self._last_mtime: float = 0.0
        self._load()

    def set_bot(self, bot: "TelegramBot"):
        """Inyecta el bot después de la construcción (útil cuando main.py los inicializa por separado)."""
        self._bot = bot

    def _load(self):
        if self._filepath.exists():
            try:
                with open(self._filepath, "r") as f:
                    data = yaml.safe_load(f) or {}
                afiliacion = data.get("afiliacion", {})
                self.gssi      = str(afiliacion.get("gssi", ""))
                raw_scan_list  = afiliacion.get("scan_list") or None
                self.scan_list = str(raw_scan_list) if raw_scan_list else None
                self._last_mtime = self._filepath.stat().st_mtime
                scan_log = self.scan_list or "(ninguna)"
                logger.info(f"Afiliación cargada — gssi='{self.gssi}', scan_list='{scan_log}'")
            except yaml.YAMLError as e:
                logger.error(f"Error leyendo afiliacion config: {e}")
                self.gssi = ""
                self.scan_list = None
        else:
            logger.warning(f"No existe afiliacion.yaml en {self._filepath}, usando valores vacíos")

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
        prev_gssi      = self.gssi
        prev_scan_list = self.scan_list
        self._load()
        changed = (self.gssi != prev_gssi) or (self.scan_list != prev_scan_list)
        if changed:
            logger.info(
                f"[AfiliacionConfig] Cambio detectado — "
                f"gssi: '{prev_gssi}'->'{self.gssi}', "
                f"scan_list: '{prev_scan_list or '(ninguna)'}' -> '{self.scan_list or '(ninguna)'}'"
            )
        return changed

    def save(self):
        try:
            with open(self._filepath, "w") as f:
                yaml.safe_dump({
                    "afiliacion": {
                        "gssi":      self.gssi,
                        "scan_list": self.scan_list,
                    }
                }, f)
            self._last_mtime = self._filepath.stat().st_mtime
            logger.info(f"Afiliacion config guardada en {self._filepath}")
        except Exception as e:
            logger.error(f"No se pudo guardar afiliacion config: {e}")

    def update_gssi(self, gssi: str):
        if not _RE_GSSI.match(gssi):
            raise ValueError(f"Formato de GSSI inválido: '{gssi}' (solo dígitos, máx 8)")
        anterior = self.gssi
        logger.info(f"Actualizando GSSI activo a: {gssi}")
        self.gssi = gssi
        self.save()
        if self._bot and gssi != anterior:
            self._bot.notificar_cambio_afiliacion("GSSI", anterior or None, gssi)

    def update_scan_list(self, scan_list: str | None):
        """
        Actualiza la scan list activa.
        Pasar None o string vacío desactiva la lista de escaneo.
        """
        if scan_list:
            if not _RE_SCAN_LIST.match(scan_list):
                raise ValueError(f"Formato de scan list inválido: '{scan_list}' (alfanumérico y guión, máx 32)")
        anterior = self.scan_list
        self.scan_list = scan_list if scan_list else None
        logger.info(f"Actualizando scan list activa a: {self.scan_list or '(ninguna)'}")
        self.save()
        if self._bot and self.scan_list != anterior:
            self._bot.notificar_cambio_afiliacion("Scan List", anterior, self.scan_list)
