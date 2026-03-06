import subprocess
import logging
import numpy as np

logger = logging.getLogger(__name__)

class BaseAudioStreamer:
    def __init__(self, samplerate=16000, channels=1):
        self.samplerate = samplerate
        self.channels = channels
        self.process = None

    def start(self):
        raise NotImplementedError

    def send_audio(self, audio_chunk: np.ndarray):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(audio_chunk.astype(np.float32).tobytes())
            except Exception:
                logger.exception("Error enviando audio al stream")

    def stop(self):
        if self.process:
            try:
                self.process.stdin.close()
                self.process.wait()
                logger.info("Stream detenido")
            except Exception:
                logger.exception("Error cerrando FFmpeg")