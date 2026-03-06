import logging
import time

logger = logging.getLogger(__name__)

class PEIDaemon:
    def __init__(self, motorola_pei_cls, audio_buffer, stt_processor, keyword_filter, db, bot, port="", baudrate=9600):
        self.motorola_pei_cls = motorola_pei_cls
        self.audio_buffer = audio_buffer
        self.stt_processor = stt_processor
        self.keyword_filter = keyword_filter
        self.db = db
        self.bot = bot
        self.port = port
        self.baudrate = baudrate
        self.radio = None

        self._init_radio()

    def _init_radio(self):
        puerto = self.port or "/dev/ttyUSB0"  # detección simple
        try:
            self.radio = self.motorola_pei_cls(puerto, self.baudrate)
            logger.info(f"Motorola PEI inicializado en {puerto}")
        except Exception as e:
            logger.critical(f"No se pudo inicializar PEI en {puerto}: {e}")
            self.radio = None

    def escuchar_pei(self, streamer=None):
        # Siempre habrá AudioBuffer aquí
        try:
            self.audio_buffer.start_buffer()
            logger.info("AudioBuffer iniciado")
        except Exception as e:
            logger.critical(f"No se pudo iniciar AudioBuffer: {e}")
            raise RuntimeError("AudioBuffer no disponible, no se pueden procesar llamadas")

        logger.info("PEI daemon corriendo...")
        while True:
            # Simulación de escucha del PEI
            time.sleep(1)
            # Enviar audio al streamer si existe
            if streamer:
                chunk = self.audio_buffer.get_chunk()
                if chunk is not None:
                    streamer.send_audio(chunk)

    def shutdown(self, streamer=None):
        logger.info("Cerrando PEI daemon...")
        if streamer:
            streamer.stop()
        if self.audio_buffer:
            self.audio_buffer.stop()