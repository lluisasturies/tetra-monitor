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

mock_websockets = mock.MagicMock()
mock_opuslib    = mock.MagicMock()
mock_opuslib.Encoder.return_value = mock.MagicMock()
mock_opuslib.APPLICATION_VOIP     = "voip"
sys.modules.setdefault("websockets", mock_websockets)
sys.modules.setdefault("opuslib",   mock_opuslib)

from pei.models.pei_event import PEIEvent          # noqa: E402
from pei.daemon.pei_daemon import PEIDaemon        # noqa: E402
from streaming.zello_streamer import ZelloStreamer  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
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
# _handle_event - actualizacion de last_event_time
# ---------------------------------------------------------------------------

def test_handle_event_actualiza_last_event_time(daemon):
    before = daemon._last_event_time
    time.sleep(0.01)
    daemon._handle_event(PEIEvent(type="PTT_START"))
    assert daemon._last_event_time > before


# ---------------------------------------------------------------------------
# _handle_event - PTT_START / PTT_END sin Zello
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
# _handle_event - PTT_START / PTT_END con Zello
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


def test_ciclo_completo_ptt_con_zello(daemon, zello):
    daemon.audio_buffer.stop_recording.return_value = "/tmp/audio.flac"
    daemon._executor = mock.MagicMock()

    daemon._handle_event(PEIEvent(type="PTT_START"), streamer=zello)
    assert daemon.audio_buffer.start_recording.called
    assert zello.call_start.called

    daemon._handle_event(PEIEvent(type="PTT_END"), streamer=zello)
    assert daemon.audio_buffer.stop_recording.called
    assert zello.call_end.called
    assert daemon._executor.submit.called


# ---------------------------------------------------------------------------
# _handle_call_start - CALL_START / CALL_END / CALL_CONNECTED
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
# _handle_call_start - mensaje de texto a Zello
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
    zello.send_text_message.assert_called_once()
    msg = zello.send_text_message.call_args[0][0]
    assert "99999" in msg
    assert "777" in msg
    assert "(" not in msg


def test_call_start_envia_texto_sin_grupos_db(zello):
    d = _make_daemon(grupos_db=None)
    d._handle_event(PEIEvent(type="CALL_START", grupo=36001, ssi=12345), streamer=zello)
    zello.send_text_message.assert_called_once()
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
