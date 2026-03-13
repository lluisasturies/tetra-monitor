import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from core.logger import logger, calls_logger
from core.afiliacion import AfiliacionConfig
from audio.audio_cleanup import AudioCleanup
from pei.models.pei_event import PEIEvent
from db.llamadas import LlamadasDB

# ZelloStreamer se importa de forma lazy dentro de los metodos que lo necesitan
# para evitar que sus dependencias opcionales (websockets, opuslib, numpy)
# rompan la importacion del modulo en entornos sin esas librerias (p.ej. CI).

# Importacion a nivel de modulo para que monkeypatch.setattr funcione en tests.
# En produccion, app_state se inicializa en main.py antes de construir PEIDaemon.
try:
    from app_state import app_state
except ImportError:  # pragma: no cover
    app_state = None  # type: ignore[assignment]

AFILIACION_CHECK_INTERVAL = 5
STT_MAX_WORKERS = 1
WATCHDOG_POLL_INTERVAL = 1  # segundos entre comprobaciones del hilo watchdog


def _is_zello(streamer) -> bool:
    """Comprueba si el streamer es una instancia de ZelloStreamer sin importar
    el modulo a nivel de paquete (import lazy)."""
    return type(streamer).__name__ == "ZelloStreamer"


class PEIDaemon:
    def __init__(self, motorola_pei_cls, audio_buffer, stt_processor, keyword_filter,
                 llamadas_db: LlamadasDB, afiliacion: AfiliacionConfig, bot, email=None,
                 grupos_db=None,
                 port="", baudrate=9600, audio_output_dir="", retention_days=7,
                 recording_enabled=True, processing_enabled=True, save_all_calls=False,
                 watchdog_timeout=60, max_recording_seconds=120):
        self.motorola_pei_cls    = motorola_pei_cls
        self.audio_buffer        = audio_buffer
        self.stt_processor       = stt_processor
        self.keyword_filter      = keyword_filter
        self.llamadas_db         = llamadas_db
        self.afiliacion          = afiliacion
        self.bot                 = bot
        self.email               = email
        self.grupos_db           = grupos_db
        self.port                = port
        self.baudrate            = baudrate
        self.recording_enabled   = recording_enabled
        self.processing_enabled  = processing_enabled
        self.save_all_calls      = save_all_calls
        self.watchdog_timeout    = watchdog_timeout
        self.max_recording_seconds = max_recording_seconds

        self.radio                  = None
        self._last_afiliacion_check = 0.0
        self._last_event_time       = time.monotonic()
        self._current_grupo         = 0
        self._current_ssi           = 0
        self._recording_start       = 0.0
        self._recording_start_time  = None
        self._executor              = ThreadPoolExecutor(max_workers=STT_MAX_WORKERS)
        self._cleanup               = AudioCleanup(audio_output_dir, retention_days)

        self._stop_event          = threading.Event()
        self._reconnect_requested = threading.Event()
        self._watchdog_thread     = None

        self._init_radio()

    # ------------------------------------------------------------------
    # Estado de conexion de la radio
    # ------------------------------------------------------------------

    def _set_radio_connected(self, connected: bool):
        if connected == app_state.radio_connected:
            return
        app_state.radio_connected = connected
        if self.bot is not None:
            self.bot.radio_active = connected
        if self.email:
            if connected:
                self.email.notificar_radio_conectada()
            else:
                self.email.notificar_radio_desconectada()

    # ------------------------------------------------------------------
    # Watchdog en hilo dedicado
    # ------------------------------------------------------------------

    def _start_watchdog(self):
        if self.watchdog_timeout <= 0:
            return
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name="pei-watchdog"
        )
        self._watchdog_thread.start()
        logger.info(f"[Watchdog] Hilo iniciado (timeout={self.watchdog_timeout}s)")

    def _watchdog_loop(self):
        while not self._stop_event.is_set():
            if app_state and app_state.radio_connected:
                elapsed = time.monotonic() - self._last_event_time
                if elapsed > self.watchdog_timeout:
                    logger.warning(
                        f"[Watchdog] Sin eventos en {elapsed:.0f}s "
                        f"(limite={self.watchdog_timeout}s) -- solicitando reconexion"
                    )
                    self._reconnect_requested.set()
            self._stop_event.wait(WATCHDOG_POLL_INTERVAL)

    # ------------------------------------------------------------------
    # Grabacion con timeout explicito
    # ------------------------------------------------------------------

    def _check_recording_timeout(self):
        if self.max_recording_seconds <= 0 or self._recording_start_time is None:
            return
        elapsed = time.monotonic() - self._recording_start_time
        if elapsed > self.max_recording_seconds:
            logger.warning(
                f"[PEI] Grabacion supera limite ({elapsed:.0f}s > {self.max_recording_seconds}s)"
                " -- cortando"
            )
            filename = f"{self._current_grupo}_{self._current_ssi}_{int(time.time())}.flac"
            path = self.audio_buffer.stop_recording(filename)
            self._recording_start_time = None
            if path:
                grupo = self._current_grupo
                ssi   = self._current_ssi
                self._executor.submit(self._process_audio, path, grupo, ssi)

    def _abort_recording(self):
        """Aborta la grabacion activa sin procesarla (sin STT)."""
        if self._recording_start_time is None:
            return
        self._recording_start_time = None
        self.audio_buffer.abort_recording()
        logger.info("[PEI] Grabacion abortada (sin STT)")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _grupo_label(self, gssi: int) -> str:
        if self.grupos_db:
            nombre = self.grupos_db.get_nombre(gssi)
            if nombre != str(gssi):
                return f"{nombre} ({gssi})"
        return str(gssi)

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
            self._set_radio_connected(True)
        except Exception as e:
            logger.critical(f"No se pudo inicializar PEI en {puerto}: {e}")
            self.radio = None
            self._set_radio_connected(False)

    def _reconnect_radio(self):
        logger.warning("[PEI] Intentando reconectar radio...")
        self._set_radio_connected(False)
        self._reconnect_requested.clear()
        try:
            if self.radio:
                self.radio.close()
        except Exception:
            pass
        self.radio = None
        time.sleep(5)
        try:
            self._init_radio()
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
                if tiene_keyword:
                    self.llamadas_db.guardar(grupo, ssi, texto, path)
                    self.bot.enviar_alerta(grupo, ssi, texto)
                else:
                    try:
                        os.remove(path)
                    except Exception as e:
                        logger.warning(f"No se pudo eliminar audio sin keyword {path}: {e}")
        except Exception as e:
            logger.error(f"Error en transcripcion async (grupo={grupo}, ssi={ssi}): {e}")

    # ------------------------------------------------------------------
    # Handlers de eventos
    # ------------------------------------------------------------------

    def _handle_ptt_start(self, streamer=None):
        logger.info(f"PTT START -- Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
        calls_logger.info(f"PTT_START | grupo={self._current_grupo} | ssi={self._current_ssi}")

        if self.recording_enabled:
            self.audio_buffer.start_recording()
            now = time.monotonic()
            self._recording_start      = now
            self._recording_start_time = now

        if _is_zello(streamer):
            streamer.call_start()

    def _handle_ptt_end(self, streamer=None):
        logger.info(f"PTT END -- Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
        calls_logger.info(f"PTT_END | grupo={self._current_grupo} | ssi={self._current_ssi}")

        if _is_zello(streamer):
            streamer.call_end()

        self._recording_start_time = None

        if self.recording_enabled:
            filename = f"{self._current_grupo}_{self._current_ssi}_{int(time.time())}.flac"
            path = self.audio_buffer.stop_recording(filename)
            if path:
                grupo = self._current_grupo
                ssi   = self._current_ssi
                self._executor.submit(self._process_audio, path, grupo, ssi)

    def _handle_call_start(self, evento: PEIEvent, streamer=None):
        self._current_grupo = evento.grupo
        self._current_ssi   = evento.ssi
        logger.info(f"CALL START -- Grupo: {self._current_grupo}, SSI: {self._current_ssi}")
        calls_logger.info(f"CALL_START | grupo={self._current_grupo} | ssi={self._current_ssi}")

        if _is_zello(streamer):
            label = self._grupo_label(self._current_grupo)
            texto = f"[TETRA] Grupo: {label} | SSI: {self._current_ssi}"
            streamer.send_text_message(texto)

    def _handle_event(self, event: PEIEvent, streamer=None):
        if not self.processing_enabled:
            return

        self._last_event_time = time.monotonic()

        if event.type == "PTT_START":
            self._handle_ptt_start(streamer)
        elif event.type == "PTT_END":
            self._handle_ptt_end(streamer)
        elif event.type == "CALL_START":
            self._handle_call_start(event, streamer)
        elif event.type == "CALL_CONNECTED":
            logger.info(f"CALL CONNECTED -- Grupo: {self._current_grupo}")
            calls_logger.info(f"CALL_CONNECTED | grupo={self._current_grupo} | ssi={self._current_ssi}")
        elif event.type == "CALL_END":
            logger.info(f"CALL END -- Grupo: {self._current_grupo}")
            calls_logger.info(f"CALL_END | grupo={self._current_grupo} | ssi={self._current_ssi}")
            # Abortar grabacion si hay una activa al terminar la llamada sin PTT_END
            self._abort_recording()
            self._current_grupo = 0
            self._current_ssi   = 0
        elif event.type == "TX_DEMAND":
            logger.debug("[PEI] TX_DEMAND recibido")

    # ------------------------------------------------------------------
    # Bucle principal
    # ------------------------------------------------------------------

    def escuchar_pei(self, streamer=None):
        try:
            self.audio_buffer.start_buffer()
        except Exception as e:
            logger.critical(f"No se pudo iniciar AudioBuffer: {e}")
            raise RuntimeError("AudioBuffer no disponible")

        self._start_watchdog()
        logger.info("PEI corriendo, esperando eventos...")

        while True:
            try:
                if self._reconnect_requested.is_set():
                    self._reconnect_radio()

                if self.radio is None:
                    self._reconnect_radio()
                    time.sleep(2)
                    continue

                self._check_afiliacion()
                self._check_recording_timeout()
                self.keyword_filter.reload_if_changed()
                self._cleanup.run_if_due()

                event = self.radio.read_event()
                if event:
                    self._handle_event(event, streamer)

                if streamer and not _is_zello(streamer):
                    chunk = self.audio_buffer.get_chunk()
                    if chunk is not None:
                        streamer.send_audio(chunk)
                elif _is_zello(streamer) and streamer._in_call:
                    chunk = self.audio_buffer.get_chunk()
                    if chunk is not None:
                        streamer.send_audio(chunk)

                time.sleep(0.05)

            except OSError as e:
                logger.error(f"[PEI] Error de puerto serie: {e}")
                self._reconnect_radio()
            except Exception as e:
                logger.error(f"Error en bucle PEI: {e}")
                time.sleep(1)

    def shutdown(self, streamer=None):
        logger.info("Apagando PEI...")
        self._stop_event.set()
        self._set_radio_connected(False)
        self._executor.shutdown(wait=True)

        if streamer:
            try:
                streamer.stop()
            except Exception as e:
                logger.error(f"Error al detener el streamer: {e}")
        if self.audio_buffer:
            self.audio_buffer.stop()
        if self.radio:
            self.radio.close()
