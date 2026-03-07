import subprocess
from core import logger

class BaseStreamer:
    def __init__(self, url, samplerate=48000, channels=1):
        self.url = url
        self.samplerate = samplerate
        self.channels = channels

        self.process = None
        self.running = False

    def build_ffmpeg_cmd(self):
        raise NotImplementedError

    def start(self):
        cmd = self.build_ffmpeg_cmd()

        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )

        self.running = True
        logger.info(f"Streaming iniciado -> {self.url}")

    def write(self, audio):
        if not self.running or not self.process:
            return

        try:
            self.process.stdin.write(audio.tobytes())
        except Exception as e:
            logger.error(f"Error enviando audio: {e}")
            self.restart()

    def restart(self):
        logger.warning("Reiniciando streamer")

        self.stop()
        self.start()

    def stop(self):
        self.running = False

        if self.process:
            self.process.kill()
            self.process = None