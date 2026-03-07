import yaml
import os
from core.logger import logger


class KeywordFilter:
    def __init__(self, filepath: str = "config/keywords.yaml"):
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"No se encontró el archivo {filepath}")
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
        self.keywords = [k.lower() for k in data.get("keywords", [])]
        logger.info(f"KeywordFilter cargado con {len(self.keywords)} palabras clave")

    def contiene_evento(self, texto: str) -> bool:
        texto = texto.lower()
        return any(k in texto for k in self.keywords)
