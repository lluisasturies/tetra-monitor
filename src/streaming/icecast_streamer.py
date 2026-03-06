from .base_streamer import BaseAudioStreamer
import subprocess
import logging

logger = logging.getLogger(__name__)

class IcecastStreamer(BaseAudioStreamer):
    def __init__(self, url, samplerate=16000, channels=1):
        super().__init__(samplerate, channels)
        self.url = url
        self.codec = "libmp3lame"
        self.fmt = "mp3"

    def start(self):
        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-f", "f32le",
            "-ar", str(self.samplerate),
            "-ac", str(self.channels),
            "-i", "pipe:0",
            "-acodec", self.codec,
            "-b:a", "128k",
            "-f", self.fmt,
            self.url
        ]
        try:
            self.process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
            logger.info(f"Streaming Icecast iniciado en {self.url}")
        except Exception:
            logger.exception("Error iniciando Icecast FFmpeg")