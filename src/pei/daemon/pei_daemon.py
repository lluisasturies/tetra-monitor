import os
import time
from concurrent.futures import ThreadPoolExecutor
from core.logger import logger, calls_logger
from core.afiliacion import AfiliacionConfig
from audio.audio_cleanup import AudioCleanup
from pei.models.pei_event import PEIEvent
from db.llamadas import LlamadasDB
from streaming.zello_streamer import ZelloStreamer

AFILIACION_CHECK_INTERVAL = 5
STT_MAX_WORKERS = 1


class PEIDaemon:
    def __init__(self, motorola_pei_cls, audio_buffer, stt_processor, keyword_filter,
                 llamadas_db: LlamadasDB, afiliacion: AfiliacionConfig, bot, email=None,
                 port="", baudrate=9600, audio_output_dir="", retention_days=7,
                 recording_enabled=True, processing_enabled=True, save_all_calls=False,
                 watchdog_timeout=60, max_recording_seconds=120):
        self.motorola_pei_cls = motorola_pei_cls
        self.audio_buffer = audio_buffer
        self.stt_processor = stt_processor
        self.keyword_filter = keyword_filter
        self.llamadas_db = llamadas_db
        self.afiliacion = afiliacion
        self.bot = bot
        self.email = email
        self.port = port
        self.baudrate = baudrate
        self.recording_enabled = recording_enabled
        self.processing_enabled = processing_enabled
        self.save_all_calls = save_all_calls
        self.watchdog_timeout = watchdog_timeout
        self.max_recording_seconds = max_recording_seconds
        self.radio = None
        self._last_afiliacion_check = 0.0
        self._last_event_time = time.monotonic()
        self._current_grupo = 0
        self._current_ssi = 0
        self._recording_start = 0.0
        self._executor = ThreadPoolExecutor(max_workers=STT_MAX_WORKERS)
        self._cleanup = AudioCleanup(audio_output_dir, retention_days)
        self._init_radio()

    def _apply_afiliacion(self):
        logger.info(
            f"[PEI] Aplicando afiliacion -- "
            f"gssi='{self.afiliacion.gssi}', scan_list='{self.afiliacion.scan_list}'"
        )
        if self.afiliacion.gssi:
            self.radio.set_active_gssi(self.afiliacion.gssi)
        if self.afiliacion.scan_list:
            self.radio.set_scan_list(self.afiliacion.scan_list)

    def _init_radio(self):
        puerto = self.port or "/dev/ttyUSB0"
        try:
            self.radio = self.motorola_pei_cls(puerto, self.baudrate)
            logger.info(f"Motorola PEI inicializado en {puerto}")
            self._apply_afiliacion()
            self.bot.radio_active = True
            logger.info("[Telegram] Alertas activadas -- radio conectada")
        except Exception as e:
            logger.critical(f"No se pudo inicializar PEI en {puerto}: {e}")
            self.radio = None
            self.bot.radio_active = False

    def _reconnect_radio(self):
        logger.warning("[PEI] Intentando reconectar radio...")
        self.bot.radio_active = False
        try:
            if self.radio:
                self.radio.close()
        except Exception:
            pass
        self.radio = None
        time.sleep(5)
        try:
            self._init_radio()
            logger.info("[PEI] Reconexion exitosa")
        except Exception as e:
            logger.error(f"[PEI] Reconexion fallida: {e}")

    def _check_afiliacion(self):
        now = time.monotonic()
        if now - self._last_afiliacion_check < AFILIACION_CHECK_INTERVAL:
            return
        self._last_afiliacion_check = now
        if self.afiliacion.reload_if_changed():
            if self.radio:
                self._apply_afiliacion()

    def _check_watchdog(self):
        if self.watchdog_timeout <= 0:
            return
        if time.monotonic() - self._last_event_time > self.watchdog_timeout:
            logger.warning(f"[PEI] Watchdog: sin eventos en {self.watchdog_timeout}s, reconectando...")
            self._reconnect_radio()
            self._last_event_time = time.monotonic()

    def _check_max_recording(self):
        if self.max_recording_seconds <= 0 or not self.audio_buffer.is_recording:
            return
        if time.monotonic() - self._recording_start > self.max_recording_seconds:
            logger.warning(f"[PEI] Limite de grabacion alcanzado ({self.max_recording_seconds}s), forzando PTT_END")
            self._handle_ptt_end(streamer=None)

    def _process_audio(self, path: str, grupo: int, ssi: int):
        try:
            texto = self.stt_processor.transcribe(path)
            logger.info(f"Transcripcion (grupo={grupo}, ssi={ssi}): {texto}")
            calls_logger.info(f"TRANSCRIPCION | grupo={grupo} | ssi={ssi} | texto=\"{texto}\"")

            tiene_keyword = self.keyword_filter.contiene_evento(texto)

            if self.save_all_calls:
                self.llamadas_db.guardar(grupo, ssi, texto, path)
                if tiene_keyword:
                    self.bot.enviar_alerta(grupo, ssi, texto)
                else:
                    logger.debug(f"Llamada guardada sin keyword (grupo={grupo}, ssi={ssi})")
            else:
                if tiene_keyword:
                    self.llamadas_db.guardar(grupo, ssi, texto, path)
                    self.bot.enviar_alerta(grupo, ssi, texto)
                else:
                    try:
                        os.remove(path)
                        logger.debug(f"Audio sin keyword eliminado: {path}")
                    except Exception as e:
                        logger.warning(f"No se pudo eliminar audio sin keyword {path}: {e}")

        except Exception as e:
            logger.error(f"Error en transcripcion async (grupo={grupo}, ssi={ssi}): {e}")

    # ------------------------------------------------------------------
    # Handlers de eventos PTT separados para mayor claridad
    # ------------------------------------------------------------------

    def _handle_ptt_start(self, streamer=None):
        logger.info(f"PTT START -- Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
        calls_logger.info(f"PTT_START | grupo={self._current_grupo} | ssi={self._current_ssi}")

        if self.recording_enabled:
            self.audio_buffer.start_recording()
            self._recording_start = time.monotonic()
        else:
            logger.debug("[PEI] PTT START ignorado -- grabacion desactivada")

        # Zello: abrir stream PTT en el canal
        if isinstance(streamer, ZelloStreamer):
            streamer.call_start()

    def _handle_ptt_end(self, streamer=None):
        logger.info(f"PTT END -- Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
        calls_logger.info(f"PTT_END | grupo={self._current_grupo} | ssi={self._current_ssi}")

        # Zello: cerrar stream PTT en el canal
        if isinstance(streamer, ZelloStreamer):
            streamer.call_end()

        if self.recording_enabled:
            filename = f"{self._current_grupo}_{self._current_ssi}_{int(time.time())}.flac"
            path = self.audio_buffer.stop_recording(filename)
            if path:
                grupo = self._current_grupo
                ssi   = self._current_ssi
                self._executor.submit(self._process_audio, path, grupo, ssi)
                logger.debug(f"Transcripcion encolada para {path}")
        else:
            logger.debug("[PEI] PTT END ignorado -- grabacion desactivada")

    def _handle_event(self, event: PEIEvent, streamer=None):
        if not self.processing_enabled:
            logger.debug(f"[PEI] Evento ignorado (processing_enabled=false): {event.type}")
            return

        self._last_event_time = time.monotonic()

        if event.type == "PTT_START":
            self._handle_ptt_start(streamer)

        elif event.type == "PTT_END":
            self._handle_ptt_end(streamer)

        elif event.type == "CALL_START":
            self._current_grupo = event.grupo
            self._current_ssi   = event.ssi
            logger.info(f"CALL START -- Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            calls_logger.info(f"CALL_START | grupo={self._current_grupo} | ssi={self._current_ssi}")

        elif event.type == "CALL_CONNECTED":
            logger.info(f"CALL CONNECTED -- Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            calls_logger.info(f"CALL_CONNECTED | grupo={self._current_grupo} | ssi={self._current_ssi}")

        elif event.type == "CALL_END":
            logger.info(f"CALL END -- Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
            calls_logger.info(f"CALL_END | grupo={self._current_grupo} | ssi={self._current_ssi}")
            self._current_grupo = 0
            self._current_ssi   = 0

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

                self._check_afiliacion()
                self._check_watchdog()
                self._check_max_recording()
                self.keyword_filter.reload_if_changed()
                self._cleanup.run_if_due()

                event = self.radio.read_event()
                if event:
                    self._handle_event(event, streamer)

                # Audio continuo para RTMP/Icecast (Zello no usa este path)
                if streamer and not isinstance(streamer, ZelloStreamer):
                    chunk = self.audio_buffer.get_chunk()
                    if chunk is not None:
                        streamer.send_audio(chunk)
                elif isinstance(streamer, ZelloStreamer) and streamer._in_call:
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
        self.bot.radio_active = False
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
