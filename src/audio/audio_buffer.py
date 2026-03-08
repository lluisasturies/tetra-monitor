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

        # Cola de pre-buffer para grabación — tamaño fijo, descarta el chunk más antiguo si está llena
        self._record_buffer = queue.Queue(maxsize=prebuffer_seconds * sample_rate)

        # Cola para streaming — sin límite de tamaño, el streamer la drena a su ritmo
        self._stream_queue = queue.Queue()

        self.recording = False
        self.frames = []
        self._stream = None
        os.makedirs(self.output_dir, exist_ok=True)

    def start_buffer(self):
        def callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"AudioBuffer status: {status}")

            chunk = indata.copy()

            # Cola de grabación: pre-buffer circular
            if self._record_buffer.full():
                self._record_buffer.get_nowait()
            self._record_buffer.put_nowait(chunk)

            # Cola de streaming: independiente, no afecta a la grabación
            try:
                self._stream_queue.put_nowait(chunk)
            except queue.Full:
                pass  # Si el streamer no consume, descartamos — mejor perder audio de streaming que bloquear

            # Acumular frames si estamos grabando
            if self.recording:
                self.frames.append(chunk)

        self._stream = sd.InputStream(
            device=self.device_index,
            channels=self.channels,
            samplerate=self.sample_rate,
            callback=callback
        )
        self._stream.start()
        logger.info("AudioBuffer stream iniciado")

    def start_recording(self):
        # Incluir el pre-buffer completo como inicio de la grabación
        self.frames = list(self._record_buffer.queue)
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
        """Devuelve el siguiente chunk para el streamer — cola independiente de la grabación."""
        try:
            return self._stream_queue.get_nowait()
        except queue.Empty:
            return None

    def stop(self):
        self.recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("AudioBuffer detenido correctamente")