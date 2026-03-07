import queue
import numpy as np
import sounddevice as sd
import soundfile as sf
import os
from core.logger import logger


class AudioBuffer:
    def __init__(self, device_index, sample_rate, channels, prebuffer_seconds, output_dir):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.prebuffer_seconds = prebuffer_seconds
        self.output_dir = output_dir
        self.buffer = queue.Queue(maxsize=prebuffer_seconds * sample_rate)
        self.recording = False
        self.frames = []
        self._stream = None
        os.makedirs(self.output_dir, exist_ok=True)

    def start_buffer(self):
        def callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"AudioBuffer status: {status}")
            if self.buffer.full():
                self.buffer.get()
            self.buffer.put(indata.copy())
            if self.recording:
                self.frames.append(indata.copy())

        self._stream = sd.InputStream(
            device=self.device_index,
            channels=self.channels,
            samplerate=self.sample_rate,
            callback=callback
        )
        self._stream.start()
        logger.info("AudioBuffer stream iniciado")

    def start_recording(self):
        self.frames = list(self.buffer.queue)  # pre-buffer
        self.recording = True
        logger.info("Grabación iniciada")

    def stop_recording(self, filename: str) -> str | None:
        self.recording = False
        if not self.frames:
            logger.warning("stop_recording llamado pero no hay frames grabados")
            return None

        filepath = os.path.join(self.output_dir, filename)
        try:
            data = np.concatenate(self.frames, axis=0)
            sf.write(filepath, data, self.sample_rate, format='FLAC')
            logger.info(f"Audio guardado en {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Error guardando audio: {e}")
            return None
        finally:
            self.frames = []

    def get_chunk(self):
        try:
            return self.buffer.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        self.recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("AudioBuffer detenido correctamente")
