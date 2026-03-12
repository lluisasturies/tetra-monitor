import os
import sys
import time
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from integrations.telegram_bot import TelegramBot  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bot():
    """Bot con Telegram activado y radio activa."""
    b = TelegramBot(
        token="fake_token",
        chat_id="123456",
        max_retries=2,
        enabled=True,
        alerts={"relevant_calls": True, "afiliacion_changed": True},
    )
    b.radio_active = True
    return b


@pytest.fixture
def bot_disabled():
    return TelegramBot(
        token="t", chat_id="c", enabled=False,
        alerts={"relevant_calls": True, "afiliacion_changed": True},
    )


# ---------------------------------------------------------------------------
# Hilo de envio y cola
# ---------------------------------------------------------------------------

def test_worker_hilo_arranca_como_daemon(bot):
    assert bot._worker.daemon is True
    assert bot._worker.is_alive()


def test_enviar_alerta_encola_mensaje(bot):
    with mock.patch.object(bot, "_enqueue") as mock_enqueue:
        bot.enviar_alerta(grupo=36001, ssi=12345, texto="incendio")
        mock_enqueue.assert_called_once()
        msg = mock_enqueue.call_args[0][0]
        assert "36001" in msg
        assert "12345" in msg
        assert "incendio" in msg


def test_enviar_alerta_no_encola_si_disabled(bot_disabled):
    with mock.patch.object(bot_disabled, "_enqueue") as mock_enqueue:
        bot_disabled.enviar_alerta(grupo=36001, ssi=12345, texto="test")
        mock_enqueue.assert_not_called()


def test_enviar_alerta_no_encola_si_radio_inactiva(bot):
    bot.radio_active = False
    with mock.patch.object(bot, "_enqueue") as mock_enqueue:
        bot.enviar_alerta(grupo=36001, ssi=12345, texto="test")
        mock_enqueue.assert_not_called()


def test_enviar_alerta_no_encola_si_relevant_calls_false():
    b = TelegramBot(
        token="t", chat_id="c", enabled=True,
        alerts={"relevant_calls": False},
    )
    b.radio_active = True
    with mock.patch.object(b, "_enqueue") as mock_enqueue:
        b.enviar_alerta(grupo=1, ssi=2, texto="test")
        mock_enqueue.assert_not_called()


def test_notificar_cambio_afiliacion_encola_mensaje(bot):
    with mock.patch.object(bot, "_enqueue") as mock_enqueue:
        bot.notificar_cambio_afiliacion("GSSI", "36001", "36002")
        mock_enqueue.assert_called_once()
        msg = mock_enqueue.call_args[0][0]
        assert "36001" in msg
        assert "36002" in msg


def test_notificar_cambio_afiliacion_no_encola_si_disabled(bot_disabled):
    with mock.patch.object(bot_disabled, "_enqueue") as mock_enqueue:
        bot_disabled.notificar_cambio_afiliacion("GSSI", "a", "b")
        mock_enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# _send_with_retry
# ---------------------------------------------------------------------------

def test_send_with_retry_ok_primer_intento(bot):
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 200
    with mock.patch("requests.post", return_value=mock_resp) as mock_post:
        bot._send_with_retry("Test")
        mock_post.assert_called_once()


def test_send_with_retry_reintenta_en_error_http(bot):
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 500
    with mock.patch("requests.post", return_value=mock_resp) as mock_post, \
         mock.patch("time.sleep"):
        bot._send_with_retry("Test")
        assert mock_post.call_count == bot.max_retries


def test_send_with_retry_reintenta_en_excepcion_red(bot):
    import requests
    with mock.patch("requests.post", side_effect=requests.exceptions.ConnectionError()), \
         mock.patch("time.sleep"):
        bot._send_with_retry("Test")  # no debe propagar


def test_send_with_retry_no_espera_tras_ultimo_intento(bot):
    """El sleep solo debe ocurrir entre reintentos, no despues del ultimo."""
    mock_resp = mock.MagicMock()
    mock_resp.status_code = 500
    sleep_calls = []
    with mock.patch("requests.post", return_value=mock_resp), \
         mock.patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
        bot._send_with_retry("Test")
    # max_retries=2: intento 1 -> sleep, intento 2 -> sin sleep
    assert len(sleep_calls) == bot.max_retries - 1


# ---------------------------------------------------------------------------
# Envio end-to-end via cola (sin bloquear el hilo de test)
# ---------------------------------------------------------------------------

def test_mensaje_llega_a_send_with_retry_via_cola(bot):
    """
    Verifica que un mensaje encolado llega efectivamente a _send_with_retry
    en el hilo dedicado dentro de un tiempo razonable.
    """
    sent = []
    original = bot._send_with_retry

    def _capture(msg):
        sent.append(msg)

    bot._send_with_retry = _capture
    bot._enqueue("hola desde test")

    # El hilo worker es daemon; esperamos hasta 1s a que procese el mensaje
    deadline = time.monotonic() + 1.0
    while not sent and time.monotonic() < deadline:
        time.sleep(0.01)

    assert sent == ["hola desde test"]
    bot._send_with_retry = original
