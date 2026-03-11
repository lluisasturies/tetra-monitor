import os
import time
import whisper
from core.logger import logger


class STTProcessor:
    def __init__(self, model_name: str = "base", language: str = "es", fp16: bool = False):
        """
        fp16: usar precisión media en inferencia.
              False por defecto (obligatorio en RPi/CPU ARM).
              Activar solo si se dispone de GPU compatible.
        """
        logger.info(f"Cargando modelo Whisper '{model_name}' (fp16={fp16})...")
        self.model = whisper.load_model(model_name)
        self.language = language
        self.fp16 = fp16
        logger.info(f"Modelo Whisper '{model_name}' cargado correctamente")

    def transcribe(self, filepath: str | None) -> str:
        """Transcribe un archivo de audio. Devuelve string vacío si falla."""
        if not filepath:
            logger.warning("transcribe() llamado con filepath None")
            return ""

        if not os.path.exists(filepath):
            logger.error(f"Archivo de audio no encontrado: {filepath}")
            return ""

        try:
            start = time.time()
            result = self.model.transcribe(
                filepath,
                language=self.language,
                fp16=self.fp16,
            )
            texto = result.get("text", "").strip().lower()
            elapsed = time.time() - start
            logger.info(f"Transcripción completada en {elapsed:.1f}s: '{texto}'")
            return texto
        except Exception as e:
            logger.error(f"Error transcribiendo {filepath}: {e}")
            return ""
