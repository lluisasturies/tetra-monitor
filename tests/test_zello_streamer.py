import os
import sys
import struct
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# --- Mockear dependencias opcionales antes de importar el modulo ---
mock_websockets = mock.MagicMock()
mock_opuslib   = mock.MagicMock()

mock_encoder_instance = mock.MagicMock()
mock_encoder_instance.encode.return_value = b"\x00" * 40
mock_opuslib.Encoder.return_value = mock_encoder_instance
mock_opuslib.APPLICATION_VOIP = "voip"

sys.modules["websockets"] = mock_websockets
sys.modules["opuslib"]   = mock_opuslib

from streaming.zello_streamer import ZelloStreamer, OPUS_FRAME_SIZE  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def streamer():
    """ZelloStreamer con hilo asyncio mockeado para no abrir conexiones reales."""
    with mock.patch("threading.Thread") as mock_thread:
        mock_thread.return_value = mock.MagicMock()
        s = ZelloStreamer(
            username="testuser",
            password="testpass",
            token="testtoken",
            channel="testchannel",
        )
        s.running    = True
        s._ws        = mock.MagicMock()
        s._loop      = mock.MagicMock()
        mock_future          = mock.MagicMock()
        mock_future.result.return_value = 42
        mock.patch(
            "asyncio.run_coroutine_threadsafe",
            return_value=mock_future
        ).start()
        return s


# ---------------------------------------------------------------------------
# Importacion sin dependencias
# ---------------------------------------------------------------------------

def test_importacion_falla_sin_deps():
    import streaming.zello_streamer as zmod
    original = zmod._ZELLO_DEPS_AVAILABLE
    zmod._ZELLO_DEPS_AVAILABLE = False
    try:
        with pytest.raises(RuntimeError, match="Dependencias de Zello"):
            ZelloStreamer(username="u", password="p", token="t", channel="c")
    finally:
        zmod._ZELLO_DEPS_AVAILABLE = original


# ---------------------------------------------------------------------------
# send_text_message
# ---------------------------------------------------------------------------

def test_send_text_message_envia_si_conectado(streamer):
    with mock.patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
        streamer.send_text_message("[TETRA] Grupo: Bomberos (36001) | SSI: 12345")
        mock_rcts.assert_called_once()


def test_send_text_message_ignorado_si_no_running(streamer):
    streamer.running = False
    with mock.patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
        streamer.send_text_message("test")
        mock_rcts.assert_not_called()


# ---------------------------------------------------------------------------
# call_start / call_end
# ---------------------------------------------------------------------------

def test_call_start_abre_stream(streamer):
    streamer.call_start()
    assert streamer._in_call is True
    assert streamer._stream_id == 42


def test_call_start_no_abre_si_ya_en_llamada(streamer):
    streamer._in_call    = True
    streamer._stream_id  = 99
    streamer.call_start()
    assert streamer._stream_id == 99


def test_call_start_no_actua_si_no_running(streamer):
    streamer.running = False
    streamer.call_start()
    assert streamer._in_call is False


def test_call_end_cierra_stream(streamer):
    streamer._in_call   = True
    streamer._stream_id = 42
    streamer.call_end()
    assert streamer._in_call   is False
    assert streamer._stream_id is None


def test_call_end_no_actua_si_no_en_llamada(streamer):
    streamer._in_call   = False
    streamer._stream_id = None
    streamer.call_end()


# ---------------------------------------------------------------------------
# send_audio
# ---------------------------------------------------------------------------

def test_send_audio_no_actua_si_no_en_llamada(streamer):
    import numpy as np
    streamer._in_call = False
    audio = np.zeros(960, dtype=np.float32)
    streamer.send_audio(audio)
    mock_encoder_instance.encode.assert_not_called()


def test_send_audio_no_actua_si_no_running(streamer):
    import numpy as np
    streamer._in_call = True
    streamer.running  = False
    audio = np.zeros(960, dtype=np.float32)
    streamer.send_audio(audio)
    mock_encoder_instance.encode.assert_not_called()


def test_send_audio_codifica_frame_completo(streamer):
    import numpy as np
    mock_encoder_instance.encode.reset_mock()
    streamer._in_call = True
    audio = np.ones(OPUS_FRAME_SIZE, dtype=np.float32) * 0.5
    streamer.send_audio(audio)
    mock_encoder_instance.encode.assert_called_once()


def test_send_audio_acumula_buffer_si_frame_incompleto(streamer):
    import numpy as np
    mock_encoder_instance.encode.reset_mock()
    streamer._in_call = True
    streamer._buf     = b""
    audio = np.ones(100, dtype=np.float32) * 0.5
    streamer.send_audio(audio)
    mock_encoder_instance.encode.assert_not_called()
    assert len(streamer._buf) == 100 * 2


def test_send_audio_codifica_multiples_frames(streamer):
    import numpy as np
    mock_encoder_instance.encode.reset_mock()
    streamer._in_call = True
    streamer._buf     = b""
    audio = np.ones(OPUS_FRAME_SIZE * 3, dtype=np.float32) * 0.1
    streamer.send_audio(audio)
    assert mock_encoder_instance.encode.call_count == 3


# ---------------------------------------------------------------------------
# _build_codec_header
# ---------------------------------------------------------------------------

def test_codec_header_formato_correcto(streamer):
    import base64
    header_b64 = streamer._build_codec_header()
    raw = base64.b64decode(header_b64)
    assert len(raw) == 4
    sample_rate, frames, frame_ms = struct.unpack(">HBB", raw)
    assert sample_rate == 16000
    assert frames      == 1
    assert frame_ms    == 60


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

def test_stop_cierra_llamada_activa(streamer):
    streamer._in_call   = True
    streamer._stream_id = 42
    streamer.stop()
    assert streamer._in_call is False


def test_stop_no_falla_sin_llamada_activa(streamer):
    streamer._in_call = False
    streamer.stop()


# ---------------------------------------------------------------------------
# create_streamer
# ---------------------------------------------------------------------------

def test_create_streamer_zello_prioridad_sobre_rtmp():
    with mock.patch.dict(os.environ, {
        "ZELLO_USERNAME": "u",
        "ZELLO_PASSWORD": "p",
        "ZELLO_TOKEN":    "t",
        "ZELLO_CHANNEL":  "ch",
    }):
        with mock.patch("threading.Thread"):
            with mock.patch("streaming.zello_streamer._ZELLO_DEPS_AVAILABLE", True):
                from streaming import create_streamer
                cfg = {
                    "zello":       {"enabled": True, "channel": "ch"},
                    "rtmp_url":    "rtmp://localhost/live/tetra",
                    "icecast_url": "icecast://localhost:8000/tetra",
                    "samplerate":  16000,
                    "channels":    1,
                }
                s = create_streamer(cfg)
                assert isinstance(s, ZelloStreamer)


def test_create_streamer_zello_desactivado_usa_rtmp():
    from streaming import create_streamer
    from streaming.rtmp_streamer import RTMPStreamer
    with mock.patch.object(RTMPStreamer, "__init__", return_value=None), \
         mock.patch.object(RTMPStreamer, "start",    return_value=None):
        cfg = {
            "zello":      {"enabled": False},
            "rtmp_url":   "rtmp://localhost/live/tetra",
            "samplerate": 16000,
            "channels":   1,
            "bitrate":    "128k",
        }
        result = create_streamer(cfg)
        assert isinstance(result, RTMPStreamer)


def test_create_streamer_zello_sin_credenciales_devuelve_none():
    with mock.patch.dict(os.environ, {
        "ZELLO_USERNAME": "",
        "ZELLO_PASSWORD": "",
        "ZELLO_TOKEN":    "",
        "ZELLO_CHANNEL":  "",
    }):
        from streaming import create_streamer
        cfg = {
            "zello":      {"enabled": True, "channel": ""},
            "samplerate": 16000,
            "channels":   1,
        }
        result = create_streamer(cfg)
        assert result is None
