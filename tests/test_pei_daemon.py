import os
import sys
import time
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

sys.modules.setdefault("serial",      mock.MagicMock())
sys.modules.setdefault("sounddevice", mock.MagicMock())
sys.modules.setdefault("soundfile",   mock.MagicMock())
sys.modules.setdefault("whisper",     mock.MagicMock())
sys.modules.setdefault("numpy",       mock.MagicMock())

mock_websockets = mock.MagicMock()
mock_opuslib    = mock.MagicMock()
mock_opuslib.Encoder.return_value = mock.MagicMock()
mock_opuslib.APPLICATION_VOIP     = "voip"
sys.modules.setdefault("websockets", mock_websockets)
sys.modules.setdefault("opuslib",   mock_opuslib)

from pei.models.pei_event import PEIEvent          # noqa: E402
from pei.daemon.pei_daemon import PEIDaemon        # noqa: E402
from streaming.zello_streamer import ZelloStreamer  # noqa: E402
import pei.daemon.pei_daemon as _pei_module        # noqa: E402


# ---------------------------------------------------------------------------
# app_state mock
# ---------------------------------------------------------------------------

class _FakeAppState:
    def __init__(self):
        self.radio_connected = False


@pytest.fixture(autouse=True)
def patch_app_state(monkeypatch):
    """
    Sustituye la variable 'app_state' en el namespace del modulo pei_daemon
    con una instancia fresca de _FakeAppState en cada test.
    """
    fake = _FakeAppState()
    monkeypatch.setattr(_pei_module, "app_state", fake)
    yield fake


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

def _make_grupos_db(mapping=None):
    db = mock.MagicMock()
    if mapping:
        db.get_nombre.side_effect = lambda gssi: mapping.get(gssi, str(gssi))
    else:
        db.get_nombre.side_effect = lambda gssi: str(gssi)
    return db


def _make_daemon(**kwargs) -> PEIDaemon:
    bot        = kwargs.pop("bot",        mock.MagicMock())
    email      = kwargs.pop("email",      mock.MagicMock())
    grupos_db  = kwargs.pop("grupos_db",  None)
    afiliacion = kwargs.pop("afiliacion", mock.MagicMock())
    afiliacion.gssi      = "36001"
    afiliacion.scan_list = "ListaScan1"
    afiliacion.reload_if_changed.return_value = False

    defaults = dict(
        motorola_pei_cls=mock.MagicMock(),
        audio_buffer=mock.MagicMock(),
        stt_processor=mock.MagicMock(),
        keyword_filter=mock.MagicMock(),
        llamadas_db=mock.MagicMock(),
        afiliacion=afiliacion,
        bot=bot,
        email=email,
        grupos_db=grupos_db,
        port="/dev/ttyUSB0",
        baudrate=9600,
        audio_output_dir="/tmp/audio_test",
        retention_days=7,
        recording_enabled=True,
        processing_enabled=True,
        save_all_calls=False,
        watchdog_timeout=0,
        max_recording_seconds=0,
    )
    defaults.update(kwargs)
    d = PEIDaemon(**defaults)
    d.bot.reset_mock()
    if d.email is not None:
        d.email.reset_mock()
    return d


def _make_zello_streamer() -> ZelloStreamer:
    with mock.patch("threading.Thread"):
        s = ZelloStreamer(username="u", password="p", token="t", channel="ch")
    s.running           = True
    s._in_call          = False
    s._stream_id        = None
    s._loop             = mock.MagicMock()
    s.call_start        = mock.MagicMock()
    s.call_end          = mock.MagicMock()
    s.send_audio        = mock.MagicMock()
    s.send_text_message = mock.MagicMock()
    s.stop              = mock.MagicMock()
    return s


@pytest.fixture
def daemon() -> PEIDaemon:
    return _make_daemon()


@pytest.fixture
def zello() -> ZelloStreamer:
    return _make_zello_streamer()


# ---------------------------------------------------------------------------
# _set_radio_connected
# ---------------------------------------------------------------------------

def test_set_radio_connected_true_notifica_email(patch_app_state):
    d = _make_daemon()
    patch_app_state.radio_connected = False
    d._set_radio_connected(True)
    d.email.notificar_radio_conectada.assert_called_once()
    d.email.notificar_radio_desconectada.assert_not_called()


def test_set_radio_connected_false_notifica_email(patch_app_state):
    d = _make_daemon()
    d._set_radio_connected(False)
    d.email.notificar_radio_desconectada.assert_called_once()
    d.email.notificar_radio_conectada.assert_not_called()


def test_set_radio_connected_mismo_estado_no_notifica(patch_app_state):
    d = _make_daemon()
    d._set_radio_connected(True)
    d.email.notificar_radio_conectada.assert_not_called()
    d.email.notificar_radio_desconectada.assert_not_called()


def test_set_radio_connected_sin_email_no_falla(patch_app_state):
    patch_app_state.radio_connected = False
    d = _make_daemon(email=None)
    patch_app_state.radio_connected = False
    d._set_radio_connected(True)


def test_set_radio_connected_actualiza_bot_radio_active(patch_app_state):
    d = _make_daemon()
    patch_app_state.radio_connected = False
    d.bot.radio_active = False
    d._set_radio_connected(True)
    assert d.bot.radio_active is True


# ---------------------------------------------------------------------------
# Watchdog
# ---------------------------------------------------------------------------

def test_watchdog_desactivado_no_arranca_hilo():
    d = _make_daemon(watchdog_timeout=0)
    d._start_watchdog()
    assert d._watchdog_thread is None


def test_watchdog_activado_arranca_hilo():
    d = _make_daemon(watchdog_timeout=30)
    d._start_watchdog()
    assert d._watchdog_thread is not None
    assert d._watchdog_thread.is_alive()
    d._stop_event.set()


def test_watchdog_solicita_reconexion_si_timeout(patch_app_state):
    patch_app_state.radio_connected = True
    d = _make_daemon(watchdog_timeout=1)
    d._reconnect_requested.clear()
    d._last_event_time = time.monotonic() - 10
    if patch_app_state.radio_connected:
        elapsed = time.monotonic() - d._last_event_time
        if elapsed > d.watchdog_timeout:
            d._reconnect_requested.set()
    assert d._reconnect_requested.is_set()


def test_watchdog_no_solicita_reconexion_si_reciente(patch_app_state):
    patch_app_state.radio_connected = True
    d = _make_daemon(watchdog_timeout=60)
    d._reconnect_requested.clear()
    d._last_event_time = time.monotonic()
    if patch_app_state.radio_connected:
        elapsed = time.monotonic() - d._last_event_time
        if elapsed > d.watchdog_timeout:
            d._reconnect_requested.set()
    assert not d._reconnect_requested.is_set()


def test_watchdog_no_actua_si_radio_desconectada(patch_app_state):
    d = _make_daemon(watchdog_timeout=1)
    patch_app_state.radio_connected = False
    d._reconnect_requested.clear()
    d._last_event_time = time.monotonic() - 100
    if patch_app_state.radio_connected:
        elapsed = time.monotonic() - d._last_event_time
        if elapsed > d.watchdog_timeout:
            d._reconnect_requested.set()
    assert not d._reconnect_requested.is_set()


# ---------------------------------------------------------------------------
# _check_recording_timeout y _abort_recording
# ---------------------------------------------------------------------------

def test_check_recording_timeout_no_actua_si_desactivado():
    d = _make_daemon(max_recording_seconds=0)
    d._recording_start_time = time.monotonic() - 9999
    d._executor = mock.MagicMock()
    d._check_recording_timeout()
    d.audio_buffer.stop_recording.assert_not_called()


def test_check_recording_timeout_no_actua_si_no_grabando():
    d = _make_daemon(max_recording_seconds=30)
    d._recording_start_time = None
    d._check_recording_timeout()
    d.audio_buffer.stop_recording.assert_not_called()


def test_check_recording_timeout_corta_grabacion_larga():
    d = _make_daemon(max_recording_seconds=30)
    d._recording_start_time = time.monotonic() - 60
    d.audio_buffer.stop_recording.return_value = "/tmp/audio_test/timeout.flac"
    d._executor = mock.MagicMock()
    d._check_recording_timeout()
    d.audio_buffer.stop_recording.assert_called_once()
    d._executor.submit.assert_called_once()
    assert d._recording_start_time is None


def test_check_recording_timeout_no_corta_grabacion_corta():
    d = _make_daemon(max_recording_seconds=120)
    d._recording_start_time = time.monotonic() - 5
    d._executor = mock.MagicMock()
    d._check_recording_timeout()
    d.audio_buffer.stop_recording.assert_not_called()


def test_abort_recording_descarta_grabacion_activa():
    d = _make_daemon()
    d._recording_start_time = time.monotonic()
    d._abort_recording()
    assert d._recording_start_time is None
    d.audio_buffer.abort_recording.assert_called_once()
    d.audio_buffer.stop_recording.assert_not_called()


def test_abort_recording_no_actua_si_no_grabando():
    d = _make_daemon()
    d._recording_start_time = None
    d._abort_recording()
    d.audio_buffer.abort_recording.assert_not_called()


# ---------------------------------------------------------------------------
# PTT - recording_start_time
# ---------------------------------------------------------------------------

def test_ptt_start_registra_recording_start_time():
    d = _make_daemon()
    before = time.monotonic()
    d._handle_event(PEIEvent(type="PTT_START"))
    assert d._recording_start_time is not None
    assert d._recording_start_time >= before


def test_ptt_end_limpia_recording_start_time():
    d = _make_daemon()
    d._recording_start_time = time.monotonic()
    d.audio_buffer.stop_recording.return_value = None
    d._handle_event(PEIEvent(type="PTT_END"))
    assert d._recording_start_time is None


# ---------------------------------------------------------------------------
# _handle_event - actualizacion de last_event_time
# ---------------------------------------------------------------------------

def test_handle_event_actualiza_last_event_time(daemon):
    before = daemon._last_event_time
    time.sleep(0.01)
    daemon._handle_event(PEIEvent(type="PTT_START"))
    assert daemon._last_event_time > before


# ---------------------------------------------------------------------------
# PTT_START / PTT_END sin Zello
# ---------------------------------------------------------------------------

def test_ptt_start_inicia_grabacion(daemon):
    daemon._handle_event(PEIEvent(type="PTT_START"))
    daemon.audio_buffer.start_recording.assert_called_once()


def test_ptt_start_no_graba_si_recording_disabled(daemon):
    daemon.recording_enabled = False
    daemon._handle_event(PEIEvent(type="PTT_START"))
    daemon.audio_buffer.start_recording.assert_not_called()


def test_ptt_start_ignorado_si_processing_disabled(daemon):
    daemon.processing_enabled = False
    daemon._handle_event(PEIEvent(type="PTT_START"))
    daemon.audio_buffer.start_recording.assert_not_called()


def test_ptt_start_registra_recording_start(daemon):
    before = time.monotonic()
    daemon._handle_event(PEIEvent(type="PTT_START"))
    assert daemon._recording_start >= before


def test_ptt_end_encola_transcripcion_si_hay_path(daemon):
    daemon.audio_buffer.stop_recording.return_value = "/tmp/audio_test/36001_123_000.flac"
    daemon._executor = mock.MagicMock()
    daemon._handle_event(PEIEvent(type="PTT_END"))
    daemon.audio_buffer.stop_recording.assert_called_once()
    daemon._executor.submit.assert_called_once()


def test_ptt_end_no_encola_si_stop_recording_devuelve_none(daemon):
    daemon.audio_buffer.stop_recording.return_value = None
    daemon._executor = mock.MagicMock()
    daemon._handle_event(PEIEvent(type="PTT_END"))
    daemon._executor.submit.assert_not_called()


def test_ptt_end_no_graba_si_recording_disabled(daemon):
    daemon.recording_enabled = False
    daemon._handle_event(PEIEvent(type="PTT_END"))
    daemon.audio_buffer.stop_recording.assert_not_called()


# ---------------------------------------------------------------------------
# PTT_START / PTT_END con Zello
# ---------------------------------------------------------------------------

def test_ptt_start_llama_call_start_en_zello(daemon, zello):
    daemon._handle_event(PEIEvent(type="PTT_START"), streamer=zello)
    zello.call_start.assert_called_once()


def test_ptt_end_llama_call_end_en_zello(daemon, zello):
    daemon.audio_buffer.stop_recording.return_value = None
    daemon._handle_event(PEIEvent(type="PTT_END"), streamer=zello)
    zello.call_end.assert_called_once()


def test_ptt_start_no_llama_call_start_en_streamer_no_zello(daemon):
    rtmp = mock.MagicMock(spec=["send_audio", "stop", "running"])
    daemon._handle_event(PEIEvent(type="PTT_START"), streamer=rtmp)
    assert not hasattr(rtmp, "call_start") or not rtmp.call_start.called


def test_ptt_end_no_llama_call_end_en_streamer_no_zello(daemon):
    rtmp = mock.MagicMock(spec=["send_audio", "stop", "running"])
    daemon.audio_buffer.stop_recording.return_value = None
    daemon._handle_event(PEIEvent(type="PTT_END"), streamer=rtmp)
    assert not hasattr(rtmp, "call_end") or not rtmp.call_end.called


# ---------------------------------------------------------------------------
# Tests de integracion: ciclo completo CALL_START -> PTT_START -> PTT_END
# ---------------------------------------------------------------------------

def test_ciclo_completo_ptt_con_zello(daemon, zello):
    """
    Ciclo completo de una transmision TETRA con Zello:
      CALL_START -> mensaje de texto en canal
      PTT_START  -> grabacion iniciada + stream Zello abierto
      PTT_END    -> grabacion parada + stream Zello cerrado + transcripcion encolada
    """
    daemon.audio_buffer.stop_recording.return_value = "/tmp/audio.flac"
    daemon._executor = mock.MagicMock()

    daemon._handle_event(PEIEvent(type="CALL_START", grupo=36001, ssi=12345), streamer=zello)
    assert daemon._current_grupo == 36001
    assert daemon._current_ssi   == 12345
    zello.send_text_message.assert_called_once()

    daemon._handle_event(PEIEvent(type="PTT_START"), streamer=zello)
    daemon.audio_buffer.start_recording.assert_called_once()
    zello.call_start.assert_called_once()
    assert daemon._recording_start_time is not None

    daemon._handle_event(PEIEvent(type="PTT_END"), streamer=zello)
    daemon.audio_buffer.stop_recording.assert_called_once()
    zello.call_end.assert_called_once()
    daemon._executor.submit.assert_called_once()
    assert daemon._recording_start_time is None


def test_ciclo_completo_ptt_sin_audio(daemon, zello):
    daemon.audio_buffer.stop_recording.return_value = None
    daemon._executor = mock.MagicMock()

    daemon._handle_event(PEIEvent(type="PTT_START"), streamer=zello)
    daemon._handle_event(PEIEvent(type="PTT_END"),   streamer=zello)

    zello.call_start.assert_called_once()
    zello.call_end.assert_called_once()
    daemon._executor.submit.assert_not_called()


def test_ciclo_completo_ptt_rtmp(daemon):
    rtmp = mock.MagicMock(spec=["send_audio", "stop", "running"])
    daemon.audio_buffer.stop_recording.return_value = "/tmp/audio.flac"
    daemon._executor = mock.MagicMock()

    daemon._handle_event(PEIEvent(type="PTT_START"), streamer=rtmp)
    daemon._handle_event(PEIEvent(type="PTT_END"),   streamer=rtmp)

    daemon.audio_buffer.start_recording.assert_called_once()
    daemon.audio_buffer.stop_recording.assert_called_once()
    daemon._executor.submit.assert_called_once()
    assert not hasattr(rtmp, "call_start")
    assert not hasattr(rtmp, "call_end")


def test_ciclo_call_end_resetea_grupo_y_ssi(daemon, zello):
    daemon._handle_event(PEIEvent(type="CALL_START", grupo=36001, ssi=12345), streamer=zello)
    daemon._handle_event(PEIEvent(type="PTT_START"), streamer=zello)
    daemon.audio_buffer.stop_recording.return_value = None
    daemon._handle_event(PEIEvent(type="PTT_END"),  streamer=zello)
    daemon._handle_event(PEIEvent(type="CALL_END"), streamer=zello)

    assert daemon._current_grupo == 0
    assert daemon._current_ssi   == 0


# ---------------------------------------------------------------------------
# CALL_START / CALL_END / CALL_CONNECTED
# ---------------------------------------------------------------------------

def test_call_start_actualiza_grupo_y_ssi(daemon):
    daemon._handle_event(PEIEvent(type="CALL_START", grupo=36001, ssi=12345))
    assert daemon._current_grupo == 36001
    assert daemon._current_ssi == 12345


def test_call_end_resetea_grupo_y_ssi(daemon):
    daemon._current_grupo = 36001
    daemon._current_ssi   = 12345
    daemon._handle_event(PEIEvent(type="CALL_END"))
    assert daemon._current_grupo == 0
    assert daemon._current_ssi == 0


def test_call_connected_no_modifica_estado(daemon):
    daemon._current_grupo = 36001
    daemon._current_ssi   = 12345
    daemon._handle_event(PEIEvent(type="CALL_CONNECTED"))
    assert daemon._current_grupo == 36001
    assert daemon._current_ssi == 12345


# ---------------------------------------------------------------------------
# Mensaje de texto a Zello en CALL_START
# ---------------------------------------------------------------------------

def test_call_start_envia_texto_a_zello_con_nombre_grupo(zello):
    gdb = _make_grupos_db({36001: "Bomberos BCN"})
    d = _make_daemon(grupos_db=gdb)
    d._handle_event(PEIEvent(type="CALL_START", grupo=36001, ssi=12345), streamer=zello)
    zello.send_text_message.assert_called_once()
    msg = zello.send_text_message.call_args[0][0]
    assert "Bomberos BCN" in msg
    assert "36001" in msg
    assert "12345" in msg


def test_call_start_envia_solo_gssi_si_grupo_no_en_bd(zello):
    gdb = _make_grupos_db()
    d = _make_daemon(grupos_db=gdb)
    d._handle_event(PEIEvent(type="CALL_START", grupo=99999, ssi=777), streamer=zello)
    msg = zello.send_text_message.call_args[0][0]
    assert "99999" in msg
    assert "777" in msg
    assert "(" not in msg


def test_call_start_envia_texto_sin_grupos_db(zello):
    d = _make_daemon(grupos_db=None)
    d._handle_event(PEIEvent(type="CALL_START", grupo=36001, ssi=12345), streamer=zello)
    msg = zello.send_text_message.call_args[0][0]
    assert "36001" in msg


def test_call_start_no_envia_texto_si_streamer_no_es_zello():
    rtmp = mock.MagicMock(spec=["send_audio", "stop", "running"])
    d = _make_daemon()
    d._handle_event(PEIEvent(type="CALL_START", grupo=36001, ssi=12345), streamer=rtmp)
    assert not hasattr(rtmp, "send_text_message") or not rtmp.send_text_message.called


def test_call_start_no_envia_texto_sin_streamer():
    d = _make_daemon()
    d._handle_event(PEIEvent(type="CALL_START", grupo=36001, ssi=12345))


# ---------------------------------------------------------------------------
# _grupo_label
# ---------------------------------------------------------------------------

def test_grupo_label_con_nombre_en_bd():
    gdb = _make_grupos_db({36001: "Bomberos BCN"})
    d = _make_daemon(grupos_db=gdb)
    assert d._grupo_label(36001) == "Bomberos BCN (36001)"


def test_grupo_label_sin_nombre_en_bd():
    gdb = _make_grupos_db()
    d = _make_daemon(grupos_db=gdb)
    assert d._grupo_label(99999) == "99999"


def test_grupo_label_sin_grupos_db():
    d = _make_daemon(grupos_db=None)
    assert d._grupo_label(36001) == "36001"


# ---------------------------------------------------------------------------
# _process_audio
# ---------------------------------------------------------------------------

def test_process_audio_con_keyword_guarda_y_alerta(daemon):
    daemon.stt_processor.transcribe.return_value = "incendio detectado"
    daemon.keyword_filter.contiene_evento.return_value = True
    daemon._process_audio("/tmp/audio.flac", grupo=36001, ssi=12345)
    daemon.llamadas_db.guardar.assert_called_once_with(36001, 12345, "incendio detectado", "/tmp/audio.flac")
    daemon.bot.enviar_alerta.assert_called_once_with(36001, 12345, "incendio detectado")


def test_process_audio_sin_keyword_no_guarda_ni_alerta(daemon):
    daemon.stt_processor.transcribe.return_value = "ruido de fondo"
    daemon.keyword_filter.contiene_evento.return_value = False
    with mock.patch("os.remove") as mock_remove:
        daemon._process_audio("/tmp/audio.flac", grupo=36001, ssi=12345)
        mock_remove.assert_called_once_with("/tmp/audio.flac")
    daemon.llamadas_db.guardar.assert_not_called()
    daemon.bot.enviar_alerta.assert_not_called()


def test_process_audio_save_all_calls_guarda_sin_keyword(daemon):
    daemon.save_all_calls = True
    daemon.stt_processor.transcribe.return_value = "ruido de fondo"
    daemon.keyword_filter.contiene_evento.return_value = False
    daemon._process_audio("/tmp/audio.flac", grupo=36001, ssi=12345)
    daemon.llamadas_db.guardar.assert_called_once()
    daemon.bot.enviar_alerta.assert_not_called()


def test_process_audio_save_all_calls_con_keyword_guarda_y_alerta(daemon):
    daemon.save_all_calls = True
    daemon.stt_processor.transcribe.return_value = "incendio detectado"
    daemon.keyword_filter.contiene_evento.return_value = True
    daemon._process_audio("/tmp/audio.flac", grupo=36001, ssi=12345)
    daemon.llamadas_db.guardar.assert_called_once()
    daemon.bot.enviar_alerta.assert_called_once()


def test_process_audio_error_stt_no_propaga(daemon):
    daemon.stt_processor.transcribe.side_effect = RuntimeError("STT fallo")
    daemon._process_audio("/tmp/audio.flac", grupo=36001, ssi=12345)


# ---------------------------------------------------------------------------
# _check_afiliacion
# ---------------------------------------------------------------------------

def test_check_afiliacion_no_recarga_antes_del_intervalo(daemon):
    daemon._last_afiliacion_check = time.monotonic()
    daemon._check_afiliacion()
    daemon.afiliacion.reload_if_changed.assert_not_called()


def test_check_afiliacion_recarga_si_ha_pasado_el_intervalo(daemon):
    daemon._last_afiliacion_check = 0.0
    daemon.afiliacion.reload_if_changed.return_value = False
    daemon._check_afiliacion()
    daemon.afiliacion.reload_if_changed.assert_called_once()


def test_check_afiliacion_aplica_cambios_si_hay_cambios(daemon):
    daemon._last_afiliacion_check = 0.0
    daemon.afiliacion.reload_if_changed.return_value = True
    daemon.radio = mock.MagicMock()
    daemon._check_afiliacion()
    daemon.radio.set_active_gssi.assert_called_once_with("36001")


def test_check_afiliacion_no_aplica_si_radio_none(daemon):
    daemon._last_afiliacion_check = 0.0
    daemon.afiliacion.reload_if_changed.return_value = True
    daemon.radio = None
    daemon._check_afiliacion()
