import queue
import numpy as np
import sounddevice as sd
import soundfile as sf
import os
from core.logger import logger

# Numero de samples por chunk -- debe coincidir con el blocksize de sd.InputStream
BLOCK_SIZE = 1024

# Maximo de chunks en la cola de streaming (~10s a 16kHz/1024 samples por chunk)
# Si el streamer no consume, descartamos los mas antiguos para no crecer indefinidamente
STREAM_QUEUE_MAXSIZE = 160


class AudioBuffer:
    def __init__(self, device_index, sample_rate, channels, prebuffer_seconds, output_dir):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.prebuffer_seconds = prebuffer_seconds
        self.output_dir = output_dir

        # Numero de chunks necesarios para cubrir prebuffer_seconds
        prebuffer_chunks = max(1, int(prebuffer_seconds * sample_rate / BLOCK_SIZE))

        # Cola de pre-buffer para grabacion -- tamano fijo en chunks, descarta el mas antiguo si esta llena
        self._record_buffer = queue.Queue(maxsize=prebuffer_chunks)

        # Cola para streaming -- tamano acotado; si el streamer no consume se descarta el chunk mas antiguo
        self._stream_queue = queue.Queue(maxsize=STREAM_QUEUE_MAXSIZE)

        self.recording = False
        self.frames = []
        self._stream = None
        os.makedirs(self.output_dir, exist_ok=True)

        logger.info(
            f"AudioBuffer configurado -- prebuffer: {prebuffer_seconds}s "
            f"({prebuffer_chunks} chunks x {BLOCK_SIZE} samples), "
            f"stream_queue maxsize: {STREAM_QUEUE_MAXSIZE}"
        )

    @property
    def is_recording(self) -> bool:
        """True si hay una grabacion activa. Acceso de solo lectura."""
        return self.recording

    def start_buffer(self):
        def callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"AudioBuffer status: {status}")

            chunk = indata.copy()

            # Cola de grabacion: pre-buffer circular
            if self._record_buffer.full():
                self._record_buffer.get_nowait()
            self._record_buffer.put_nowait(chunk)

            # Cola de streaming: si esta llena, descartamos el chunk mas antiguo antes de insertar
            if self._stream_queue.full():
                try:
                    self._stream_queue.get_nowait()
                except queue.Empty:
                    pass
            try:
                self._stream_queue.put_nowait(chunk)
            except queue.Full:
                pass  # carrera remota, ignoramos

            # Acumular frames si estamos grabando
            if self.recording:
                self.frames.append(chunk)

        self._stream = sd.InputStream(
            device=self.device_index,
            channels=self.channels,
            samplerate=self.sample_rate,
            blocksize=BLOCK_SIZE,
            callback=callback
        )
        self._stream.start()
        logger.info("AudioBuffer stream iniciado")

    def start_recording(self):
        # Incluir el pre-buffer completo como inicio de la grabacion
        self.frames = list(self._record_buffer.queue)
        self.recording = True
        logger.info("Grabacion iniciada")

    def stop_recording(self, filename: str) -> str | None:
        self.recording = False
        if not self.frames:
            logger.warning("stop_recording llamado pero no hay frames grabados")
            return None

        filepath = os.path.join(self.output_dir, filename)
        try:
            data = np.concatenate(self.frames, axis=0)
            sf.write(filepath, data, self.sample_rate, format="FLAC")
            logger.info(f"Audio guardado en {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Error guardando audio: {e}")
            return None
        finally:
            self.frames = []

    def abort_recording(self):
        """Descarta la grabacion en curso sin escribir nada en disco."""
        self.recording = False
        self.frames = []
        logger.warning("Grabacion abortada -- frames descartados sin escribir en disco")

    def get_chunk(self):
        """Devuelve el siguiente chunk para el streamer -- cola independiente de la grabacion."""
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
