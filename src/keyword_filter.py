import yaml
import os

class KeywordFilter:
    def __init__(self, filepath="config/keywords.yaml"):
        """
        filepath: ruta al archivo keywords.yaml
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"No se encontró el archivo {filepath}")
        with open(filepath, "r") as f:
            data = yaml.safe_load(f)
        self.keywords = [k.lower() for k in data.get("keywords", [])]

    def contiene_evento(self, texto):
        texto = texto.lower()
        return any(k in texto for k in self.keywords)