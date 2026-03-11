import os
import sys
import smtplib
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from integrations.email_notifier import EmailNotifier  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def notifier():
    return EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        user="test@example.com",
        password="secret",
        to="admin@example.com",
        use_tls=True,
        enabled=True,
        alerts={
            "startup": True,
            "shutdown": True,
            "radio_disconnected": True,
            "radio_connected": True,
        },
    )


@pytest.fixture
def smtp_mock():
    """Mock de smtplib.SMTP como context manager."""
    with mock.patch("smtplib.SMTP") as m:
        instance = mock.MagicMock()
        m.return_value.__enter__ = mock.Mock(return_value=instance)
        m.return_value.__exit__  = mock.Mock(return_value=False)
        yield m, instance


# ---------------------------------------------------------------------------
# Flags de alertas
# ---------------------------------------------------------------------------

def test_startup_desactivado_no_envia(smtp_mock):
    m, _ = smtp_mock
    n = EmailNotifier(
        smtp_host="h", smtp_port=587, user="u", password="p",
        to="a@b.com", enabled=True, alerts={"startup": False},
    )
    n.notificar_startup()
    m.assert_not_called()


def test_shutdown_desactivado_no_envia(smtp_mock):
    m, _ = smtp_mock
    n = EmailNotifier(
        smtp_host="h", smtp_port=587, user="u", password="p",
        to="a@b.com", enabled=True, alerts={"shutdown": False},
    )
    n.notificar_shutdown()
    m.assert_not_called()


def test_radio_disconnected_desactivado_no_envia(smtp_mock):
    m, _ = smtp_mock
    n = EmailNotifier(
        smtp_host="h", smtp_port=587, user="u", password="p",
        to="a@b.com", enabled=True, alerts={"radio_disconnected": False},
    )
    n.notificar_radio_desconectada()
    m.assert_not_called()


def test_radio_connected_desactivado_por_defecto(smtp_mock):
    """radio_connected es False por defecto — no debe enviar sin configurarlo."""
    m, _ = smtp_mock
    n = EmailNotifier(
        smtp_host="h", smtp_port=587, user="u", password="p",
        to="a@b.com", enabled=True, alerts={},
    )
    n.notificar_radio_conectada()
    m.assert_not_called()


def test_email_desactivado_no_envia_nada(smtp_mock, notifier):
    m, _ = smtp_mock
    notifier.enabled = False
    notifier.notificar_startup()
    notifier.notificar_shutdown()
    notifier.notificar_radio_desconectada()
    notifier.notificar_radio_conectada()
    m.assert_not_called()


# ---------------------------------------------------------------------------
# Envío correcto
# ---------------------------------------------------------------------------

def test_startup_envia_email(notifier, smtp_mock):
    _, instance = smtp_mock
    notifier.notificar_startup()
    instance.starttls.assert_called_once()
    instance.login.assert_called_once_with("test@example.com", "secret")
    instance.sendmail.assert_called_once()
    subject = instance.sendmail.call_args[0][2]
    assert "[TETRA] Sistema iniciado" in subject


def test_shutdown_envia_email(notifier, smtp_mock):
    _, instance = smtp_mock
    notifier.notificar_shutdown()
    instance.sendmail.assert_called_once()
    subject = instance.sendmail.call_args[0][2]
    assert "[TETRA] Sistema detenido" in subject


def test_radio_desconectada_envia_email(notifier, smtp_mock):
    _, instance = smtp_mock
    notifier.notificar_radio_desconectada()
    instance.sendmail.assert_called_once()
    subject = instance.sendmail.call_args[0][2]
    assert "Radio desconectada" in subject


def test_radio_conectada_envia_email(notifier, smtp_mock):
    _, instance = smtp_mock
    notifier.notificar_radio_conectada()
    instance.sendmail.assert_called_once()
    subject = instance.sendmail.call_args[0][2]
    assert "Radio reconectada" in subject


def test_destinatarios_multiples(smtp_mock):
    _, instance = smtp_mock
    n = EmailNotifier(
        smtp_host="h", smtp_port=587, user="u", password="p",
        to=["a@b.com", "c@d.com"], enabled=True,
        alerts={"startup": True},
    )
    n.notificar_startup()
    destinatarios = instance.sendmail.call_args[0][1]
    assert "a@b.com" in destinatarios
    assert "c@d.com" in destinatarios


def test_sin_tls_no_llama_starttls(smtp_mock):
    _, instance = smtp_mock
    n = EmailNotifier(
        smtp_host="h", smtp_port=25, user="u", password="p",
        to="a@b.com", use_tls=False, enabled=True,
        alerts={"startup": True},
    )
    n.notificar_startup()
    instance.starttls.assert_not_called()
    instance.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# Manejo de errores
# ---------------------------------------------------------------------------

def test_error_smtp_no_propaga(notifier):
    with mock.patch("smtplib.SMTP", side_effect=OSError("conexión rechazada")):
        notifier.notificar_startup()  # no debe lanzar excepción


def test_error_autenticacion_no_reintenta(notifier, smtp_mock):
    _, instance = smtp_mock
    instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"auth failed")
    notifier.max_retries = 3
    notifier.notificar_startup()
    # Solo debe haber intentado login una vez (sin reintentos)
    assert instance.login.call_count == 1


def test_reintento_en_error_transitorio(smtp_mock):
    _, instance = smtp_mock
    # Falla en primer intento, éxito en segundo
    instance.sendmail.side_effect = [OSError("timeout"), None]
    n = EmailNotifier(
        smtp_host="h", smtp_port=587, user="u", password="p",
        to="a@b.com", enabled=True, max_retries=3,
        alerts={"startup": True},
    )
    with mock.patch("time.sleep"):  # evitar espera real
        n.notificar_startup()
    assert instance.sendmail.call_count == 2
