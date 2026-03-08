import time
from concurrent.futures import ThreadPoolExecutor
from core.logger import logger
from core.scan_config import scan_config
from pei.models.pei_event import PEIEvent

# Cada cuántos segundos el daemon comprueba si cambió el scan config
SCAN_CONFIG_CHECK_INTERVAL = 5

# Número máximo de transcripciones en paralelo
# En RPi con Whisper base, 1 es lo razonable para no saturar la CPU
STT_MAX_WORKERS = 1

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
        self._last_config_check = 0.0
        self._current_grupo = 0
        self._current_ssi = 0
        self._executor = ThreadPoolExecutor(max_workers=STT_MAX_WORKERS)
        self._init_radio()

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
        """Comprueba si el config cambió en disco y aplica los cambios a la radio."""
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
                self.db.guardar_evento(grupo, ssi, texto, path)
                self.bot.enviar_alerta(grupo, ssi, texto)
        except Exception as e:
            logger.error(f"Error en transcripción async (grupo={grupo}, ssi={ssi}): {e}")

    def _handle_event(self, event: PEIEvent):
        if event.type == "PTT_START":
            logger.info(f"PTT START — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            self.audio_buffer.start_recording()

        elif event.type == "PTT_END":
            logger.info(f"PTT END — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            filename = f"{self._current_grupo}_{self._current_ssi}_{int(time.time())}.flac"
            path = self.audio_buffer.stop_recording(filename)

            if path:
                # Lanzar la transcripción en un hilo separado — el bucle PEI no espera
                grupo = self._current_grupo
                ssi = self._current_ssi
                self._executor.submit(self._process_audio, path, grupo, ssi)
                logger.debug(f"Transcripción encolada para {path}")

        elif event.type == "CALL_START":
            # +CTICN nos da el GSSI y SSI — los guardamos para usarlos en PTT
            self._current_grupo = event.grupo
            self._current_ssi = event.ssi
            logger.info(f"CALL START — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")

        elif event.type == "CALL_CONNECTED":
            logger.info(f"CALL CONNECTED — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")

        elif event.type == "CALL_END":
            logger.info(f"CALL END — Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
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

        # Esperar a que terminen las transcripciones en curso antes de cerrar
        logger.info("Esperando transcripciones pendientes...")
        self._executor.shutdown(wait=True)

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
        if self.radio:
            self.radio.close()