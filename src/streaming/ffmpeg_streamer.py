import os
import subprocess
import logging
import yaml
import numpy as np

logger = logging.getLogger(__name__)

# -----------------------------
# Cargar configuración streaming
# -----------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, "../../config/config.yaml")

try:
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)
        stream_cfg = cfg.get("streaming", {})
        audio_cfg = cfg.get("audio", {})
except FileNotFoundError:
    logger.critical(f"No se encontró el archivo de configuración: {config_path}")
    raise

RTMP_URL = stream_cfg.get("rtmp_url")
ICECAST_URL = stream_cfg.get("icecast_url")
SAMPLERATE = audio_cfg.get("sample_rate", 16000)
CHANNELS = audio_cfg.get("channels", 1)
ENABLED = stream_cfg.get("enabled", False)

# -----------------------------
# Clase AudioStreamer
# -----------------------------
class AudioStreamer:
    def __init__(self):
        if not ENABLED:
            logger.info("Streaming desactivado en config.yaml")
            self.process = None
            return

        self.samplerate = SAMPLERATE
        self.channels = CHANNELS
        self.output_url = RTMP_URL or ICECAST_URL
        self.process = None

        if not self.output_url:
            raise ValueError("Debes definir rtmp_url o icecast_url en config.yaml")

    def start(self):
        if not self.process:
            logger.info(f"Iniciando streaming hacia {self.output_url}")

            cmd = [
                "ffmpeg",
                "-loglevel", "error",
                "-f", "f32le",
                "-ar", str(self.samplerate),
                "-ac", str(self.channels),
                "-i", "pipe:0",
                "-acodec", "aac",
                "-b:a", "128k",
                "-f", "flv",
                self.output_url
            ]

            try:
                self.process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            except Exception:
                logger.exception("Error iniciando FFmpeg")

    def send_audio(self, audio_chunk: np.ndarray):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(audio_chunk.astype(np.float32).tobytes())
            except Exception:
                logger.exception("Error enviando audio al stream")

    def stop(self):
        if self.process:
            logger.info("Deteniendo stream")

            try:
                self.process.stdin.close()
                self.process.wait()
            except Exception:
                logger.exception("Error cerrando FFmpeg")