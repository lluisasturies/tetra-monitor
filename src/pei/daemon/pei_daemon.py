import time
from concurrent.futures import ThreadPoolExecutor
from core.logger import logger, calls_logger
from core.scan_config import scan_config
from audio.audio_cleanup import AudioCleanup
from pei.models.pei_event import PEIEvent
from db.llamadas import LlamadasDB

SCAN_CONFIG_CHECK_INTERVAL = 5
STT_MAX_WORKERS = 1


class PEIDaemon:
    def __init__(self, motorola_pei_cls, audio_buffer, stt_processor, keyword_filter,
                 llamadas_db: LlamadasDB, bot,
                 port="", baudrate=9600, audio_output_dir="", retention_days=7,
                 recording_enabled=True, processing_enabled=True):
        self.motorola_pei_cls = motorola_pei_cls
        self.audio_buffer = audio_buffer
        self.stt_processor = stt_processor
        self.keyword_filter = keyword_filter
        self.llamadas_db = llamadas_db
        self.bot = bot
        self.port = port
        self.baudrate = baudrate
        self.recording_enabled = recording_enabled
        self.processing_enabled = processing_enabled
        self.radio = None
        self._last_config_check = 0.0
        self._current_grupo = 0
        self._current_ssi = 0
        self._executor = ThreadPoolExecutor(max_workers=STT_MAX_WORKERS)
        self._cleanup = AudioCleanup(audio_output_dir, retention_days)
        self._init_radio()

        logger.info(f"Grabación de audio: {'ACTIVADA'  if self.recording_enabled  else 'DESACTIVADA'}")
        logger.info(f"Procesado PEI:      {'ACTIVADO'  if self.processing_enabled else 'DESACTIVADO'}")

    def _init_radio(self):
        puerto = self.port or "/dev/ttyUSB0"
        try:
            self.radio = self.motorola_pei_cls(puerto, self.baudrate)
            logger.info(f"Motorola PEI inicializado en {puerto}")
            if scan_config.gssi:
                self.radio.set_active_gssi(scan_config.gssi)
            if scan_config.scan_list:
                self.radio.set_scan_list(scan_config.scan_list)
        except Exception as e:
            logger.critical(f"No se pudo inicializar PEI en {puerto}: {e}")
            self.radio = None

    def _reconnect_radio(self):
        logger.warning("[PEI] Intentando reconectar radio...")
        try:
            if self.radio:
                self.radio.close()
        except Exception:
            pass
        self.radio = None
        time.sleep(5)
        try:
            self._init_radio()
            logger.info("[PEI] Reconexión exitosa")
        except Exception as e:
            logger.error(f"[PEI] Reconexión fallida: {e}")

    def _check_scan_config(self):
        now = time.monotonic()
        if now - self._last_config_check < SCAN_CONFIG_CHECK_INTERVAL:
            return
        self._last_config_check = now
        if scan_config.reload_if_changed():
            logger.info("[PEI] Aplicando nuevo scan config a la radio")
            if self.radio:
                if scan_config.gssi:
                    self.radio.set_active_gssi(scan_config.gssi)
                if scan_config.scan_list:
                    self.radio.set_scan_list(scan_config.scan_list)

    def _process_audio(self, path: str, grupo: int, ssi: int):
        """Corre en un hilo del executor — no bloquea el bucle PEI."""
        try:
            texto = self.stt_processor.transcribe(path)
            logger.info(f"Transcripción (grupo={grupo}, ssi={ssi}): {texto}")

            if self.keyword_filter.contiene_evento(texto):
                self.llamadas_db.guardar(grupo, ssi, texto, path)
                self.bot.enviar_alerta(grupo, ssi, texto)
        except Exception as e:
            logger.error(f"Error en transcripción async (grupo={grupo}, ssi={ssi}): {e}")

    def _handle_event(self, event: PEIEvent):
        if not self.processing_enabled:
            logger.debug(f"[PEI] Evento ignorado (processing_enabled=false): {event.type}")
            return

        if event.type == "PTT_START":
            logger.info(f"PTT START — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            calls_logger.info(f"PTT_START | grupo={self._current_grupo} | ssi={self._current_ssi}")
            if self.recording_enabled:
                self.audio_buffer.start_recording()
            else:
                logger.debug("[PEI] PTT START ignorado — grabación desactivada")

        elif event.type == "PTT_END":
            logger.info(f"PTT END — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            calls_logger.info(f"PTT_END | grupo={self._current_grupo} | ssi={self._current_ssi}")
            if self.recording_enabled:
                filename = f"{self._current_grupo}_{self._current_ssi}_{int(time.time())}.flac"
                path = self.audio_buffer.stop_recording(filename)
                if path:
                    grupo = self._current_grupo
                    ssi = self._current_ssi
                    self._executor.submit(self._process_audio, path, grupo, ssi)
                    logger.debug(f"Transcripción encolada para {path}")
            else:
                logger.debug("[PEI] PTT END ignorado — grabación desactivada")

        elif event.type == "CALL_START":
            self._current_grupo = event.grupo
            self._current_ssi = event.ssi
            logger.info(f"CALL START — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            calls_logger.info(f"CALL_START | grupo={self._current_grupo} | ssi={self._current_ssi}")

        elif event.type == "CALL_CONNECTED":
            logger.info(f"CALL CONNECTED — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            calls_logger.info(f"CALL_CONNECTED | grupo={self._current_grupo} | ssi={self._current_ssi}")

        elif event.type == "CALL_END":
            logger.info(f"CALL END — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            calls_logger.info(f"CALL_END | grupo={self._current_grupo} | ssi={self._current_ssi}")
            self._current_grupo = 0
            self._current_ssi = 0

        elif event.type == "TX_DEMAND":
            logger.debug("[PEI] TX_DEMAND recibido (radio transmitiendo)")

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
                if self.radio is None:
                    self._reconnect_radio()
                    time.sleep(2)
                    continue

                self._check_scan_config()
                self.keyword_filter.reload_if_changed()
                self._cleanup.run_if_due()

                event = self.radio.read_event()
                if event:
                    self._handle_event(event)

                if streamer:
                    chunk = self.audio_buffer.get_chunk()
                    if chunk is not None:
                        streamer.send_audio(chunk)

                time.sleep(0.05)

            except OSError as e:
                logger.error(f"[PEI] Error de puerto serie: {e}. Intentando reconectar...")
                self._reconnect_radio()

            except Exception as e:
                logger.error(f"Error en bucle PEI: {e}")
                time.sleep(1)

    def shutdown(self, streamer=None):
        logger.info("Apagando PEI...")
        self._executor.shutdown(wait=True)

        if streamer:
            logger.info(f"Deteniendo streaming ({streamer.__class__.__name__})")
            try:
                streamer.stop()
            except Exception as e:
                logger.error(f"Error al detener el streamer: {e}")
        if self.audio_buffer:
            self.audio_buffer.stop()
        if self.radio:
            self.radio.close()
