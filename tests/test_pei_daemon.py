import os
import sys
import time
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Mocks de hardware antes de cualquier import del proyecto
sys.modules.setdefault("serial", mock.MagicMock())
sys.modules.setdefault("sounddevice", mock.MagicMock())
sys.modules.setdefault("soundfile", mock.MagicMock())
sys.modules.setdefault("whisper", mock.MagicMock())

from pei.models.pei_event import PEIEvent  # noqa: E402
from pei.daemon.pei_daemon import PEIDaemon  # noqa: E402
from app_state import app_state  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_app_state():
    app_state.radio_connected = False
    yield
    app_state.radio_connected = False


@pytest.fixture
def daemon():
    """PEIDaemon completamente mockeado — sin hardware ni BD real."""
    motorola_cls   = mock.MagicMock()
    audio_buffer   = mock.MagicMock()
    stt_processor  = mock.MagicMock()
    keyword_filter = mock.MagicMock()
    llamadas_db    = mock.MagicMock()
    afiliacion     = mock.MagicMock()
    bot            = mock.MagicMock()

    afiliacion.gssi      = "36001"
    afiliacion.scan_list = "ListaScan1"
    afiliacion.reload_if_changed.return_value = False

    d = PEIDaemon(
        motorola_pei_cls=motorola_cls,
        audio_buffer=audio_buffer,
        stt_processor=stt_processor,
        keyword_filter=keyword_filter,
        llamadas_db=llamadas_db,
        afiliacion=afiliacion,
        bot=bot,
        port="/dev/ttyUSB0",
        baudrate=9600,
        audio_output_dir="/tmp/audio_test",
        retention_days=7,
        recording_enabled=True,
        processing_enabled=True,
        save_all_calls=False,
    )
    # Resetear llamadas al bot que ocurren durante _init_radio
    bot.reset_mock()
    return d


# ---------------------------------------------------------------------------
# _set_radio_connected — notificaciones al cambiar estado
# ---------------------------------------------------------------------------

def test_set_radio_connected_true_notifica_conectada(daemon):
    app_state.radio_connected = False
    daemon._set_radio_connected(True)
    daemon.bot.notificar_radio_conectada.assert_called_once()
    daemon.bot.notificar_radio_desconectada.assert_not_called()


def test_set_radio_connected_false_notifica_desconectada(daemon):
    app_state.radio_connected = True
    daemon.bot.radio_active = True
    daemon._set_radio_connected(False)
    daemon.bot.notificar_radio_desconectada.assert_called_once()
    daemon.bot.notificar_radio_conectada.assert_not_called()


def test_set_radio_connected_mismo_estado_no_notifica(daemon):
    app_state.radio_connected = True
    daemon._set_radio_connected(True)  # ya estaba conectada
    daemon.bot.notificar_radio_conectada.assert_not_called()
    daemon.bot.notificar_radio_desconectada.assert_not_called()


# ---------------------------------------------------------------------------
# _handle_event — PTT_START
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


# ---------------------------------------------------------------------------
# _handle_event — PTT_END
# ---------------------------------------------------------------------------

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
# _handle_event — CALL_START / CALL_END
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
# _process_audio — lógica de keyword + guardado
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
    daemon.stt_processor.transcribe.side_effect = RuntimeError("STT falló")
    daemon._process_audio("/tmp/audio.flac", grupo=36001, ssi=12345)  # no debe lanzar


# ---------------------------------------------------------------------------
# _check_afiliacion — recarga en caliente
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
    daemon._check_afiliacion()  # no debe lanzar
