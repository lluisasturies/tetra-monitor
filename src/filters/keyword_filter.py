import yaml
from pathlib import Path
from core.logger import logger


class KeywordFilter:
    def __init__(self, filepath: str = "config/keywords.yaml"):
        self._filepath = Path(filepath)
        self._last_mtime: float = 0.0
        self.keywords: list[str] = []
        if not self._filepath.exists():
            logger.warning(
                f"[KeywordFilter] {self._filepath} no existe — creando vacío"
            )
            self._create_empty()
        self._load()

    def _create_empty(self):
        """Crea un keywords.yaml vacío para que el daemon pueda arrancar."""
        try:
            self._filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self._filepath, "w") as f:
                yaml.safe_dump({"keywords": []}, f)
            logger.info(f"[KeywordFilter] Creado {self._filepath} vacío")
        except Exception as e:
            logger.error(f"[KeywordFilter] No se pudo crear {self._filepath}: {e}")

    def _load(self):
        try:
            with open(self._filepath, "r") as f:
                data = yaml.safe_load(f) or {}
            self.keywords = [k.lower() for k in data.get("keywords", [])]
            self._last_mtime = self._filepath.stat().st_mtime
            logger.info(f"KeywordFilter cargado con {len(self.keywords)} palabras clave")
        except yaml.YAMLError as e:
            logger.error(f"Error leyendo keywords.yaml: {e}")

    def reload_if_changed(self) -> bool:
        """Relee desde disco si el fichero fue modificado. Devuelve True si hubo cambios."""
        try:
            mtime = self._filepath.stat().st_mtime
        except OSError:
            return False
        if mtime <= self._last_mtime:
            return False
        prev = self.keywords.copy()
        self._load()
        changed = self.keywords != prev
        if changed:
            logger.info(f"[KeywordFilter] Keywords actualizadas: {self.keywords}")
        return changed

    def contiene_evento(self, texto: str) -> bool:
        texto = texto.lower()
        return any(k in texto for k in self.keywords)

    def save(self):
        """Persiste la lista actual de keywords en disco."""
        try:
            with open(self._filepath, "w") as f:
                yaml.safe_dump({"keywords": self.keywords}, f, allow_unicode=True)
            self._last_mtime = self._filepath.stat().st_mtime
            logger.info(f"[KeywordFilter] keywords.yaml guardado con {len(self.keywords)} entradas")
        except Exception as e:
            logger.error(f"[KeywordFilter] Error guardando keywords.yaml: {e}")
            raise

    def add(self, keyword: str) -> bool:
        """
        Añade una keyword (normalizada a minúsculas) y persiste.
        Devuelve True si se añadió, False si ya existía.
        """
        kw = keyword.strip().lower()
        if kw in self.keywords:
            return False
        self.keywords.append(kw)
        self.save()
        logger.info(f"[KeywordFilter] Keyword añadida: '{kw}'")
        return True

    def remove(self, keyword: str) -> bool:
        """
        Elimina una keyword y persiste.
        Devuelve True si se eliminó, False si no existía.
        """
        kw = keyword.strip().lower()
        if kw not in self.keywords:
            return False
        self.keywords.remove(kw)
        self.save()
        logger.info(f"[KeywordFilter] Keyword eliminada: '{kw}'")
        return True
