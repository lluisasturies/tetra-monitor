import time
from core.logger import logger


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
        puerto = self.port or "/dev/ttyUSB0"
        try:
            self.radio = self.motorola_pei_cls(puerto, self.baudrate)
            logger.info(f"Motorola PEI inicializado en {puerto}")
        except Exception as e:
            logger.critical(f"No se pudo inicializar PEI en {puerto}: {e}")
            self.radio = None

    def escuchar_pei(self, streamer=None):
        try:
            self.audio_buffer.start_buffer()
            logger.info("AudioBuffer iniciado")
        except Exception as e:
            logger.critical(f"No se pudo iniciar AudioBuffer: {e}")
            raise RuntimeError("AudioBuffer no disponible")

        logger.info("PEI corriendo, esperando eventos...")

        while True:
            try:
                event = self.radio.read_event() if self.radio else None

                if event:
                    if event.type == "PTT_START":
                        logger.info(f"PTT START — Grupo: {event.grupo}, SSI: {event.ssi}")
                        self.audio_buffer.start_recording()

                    elif event.type == "PTT_END":
                        logger.info(f"PTT END — Grupo: {event.grupo}, SSI: {event.ssi}")
                        filename = f"{event.grupo}_{event.ssi}_{int(time.time())}.flac"
                        path = self.audio_buffer.stop_recording(filename)

                        if path:
                            texto = self.stt_processor.transcribe(path)
                            logger.info(f"Transcripción: {texto}")

                            if self.keyword_filter.contiene_evento(texto):
                                self.db.guardar_evento(event.grupo, event.ssi, texto, path)
                                self.bot.enviar_alerta(event.grupo, event.ssi, texto)

                # Enviar audio al streamer si existe
                if streamer:
                    chunk = self.audio_buffer.get_chunk()
                    if chunk is not None:
                        streamer.send_audio(chunk)

                time.sleep(0.05)

            except Exception as e:
                logger.error(f"Error en bucle PEI: {e}")
                time.sleep(1)

    def shutdown(self, streamer=None):
        logger.info("Apagando PEI...")
        if streamer:
            logger.info(f"Deteniendo streaming ({streamer.__class__.__name__})")
            try:
                streamer.stop()
            except Exception as e:
                logger.error(f"Error al detener el streamer: {e}")
        if self.audio_buffer:
            self.audio_buffer.stop()
        if self.db:
            self.db.close()
