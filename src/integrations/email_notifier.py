import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from core.logger import logger


class EmailNotifier:
    """
    Notificaciones por email para eventos de sistema: startup, shutdown,
    radio_disconnected, radio_connected.

    Credenciales via variables de entorno: EMAIL_USER, EMAIL_PASSWORD.
    Configuración en config.yaml bajo 'email:'.
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        user: str,
        password: str,
        to: str | list[str],
        use_tls: bool = True,
        max_retries: int = 3,
        enabled: bool = True,
        alerts: dict | None = None,
    ):
        self.smtp_host   = smtp_host
        self.smtp_port   = smtp_port
        self.user        = user
        self.password    = password
        self.to          = [to] if isinstance(to, str) else list(to)
        self.use_tls     = use_tls
        self.max_retries = max_retries
        self.enabled     = enabled

        _a = alerts or {}
        self._alert_startup            = _a.get("startup",            True)
        self._alert_shutdown           = _a.get("shutdown",           True)
        self._alert_radio_disconnected = _a.get("radio_disconnected", True)
        self._alert_radio_connected    = _a.get("radio_connected",    False)  # off por defecto

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def notificar_startup(self):
        if not self._alert_startup:
            return
        self._send(
            subject="[TETRA] Sistema iniciado",
            body="El sistema TETRA Monitor ha arrancado correctamente y está escuchando.",
        )

    def notificar_shutdown(self):
        if not self._alert_shutdown:
            return
        self._send(
            subject="[TETRA] Sistema detenido",
            body="El sistema TETRA Monitor se ha cerrado.",
        )

    def notificar_radio_desconectada(self):
        if not self._alert_radio_disconnected:
            return
        self._send(
            subject="[TETRA] ERROR — Radio desconectada",
            body=(
                "Se ha perdido la conexión con la radio (PEI).\n"
                "El sistema intentará reconectar automáticamente.\n"
                "Revisa el hardware si el problema persiste."
            ),
        )

    def notificar_radio_conectada(self):
        if not self._alert_radio_connected:
            return
        self._send(
            subject="[TETRA] Radio reconectada",
            body="La conexión con la radio (PEI) se ha restablecido correctamente.",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _send(self, subject: str, body: str):
        """Envía un email con reintentos. No propaga excepciones."""
        if not self.enabled:
            logger.debug(f"[Email] Ignorado — email desactivado: {subject}")
            return

        for intento in range(1, self.max_retries + 1):
            try:
                msg = MIMEMultipart()
                msg["From"]    = self.user
                msg["To"]      = ", ".join(self.to)
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain", "utf-8"))

                with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as smtp:
                    if self.use_tls:
                        smtp.starttls()
                    smtp.login(self.user, self.password)
                    smtp.sendmail(self.user, self.to, msg.as_string())

                logger.info(f"[Email] Enviado: {subject}")
                return

            except smtplib.SMTPAuthenticationError as e:
                logger.error(f"[Email] Error de autenticación SMTP: {e}")
                return  # No reintentar — credenciales incorrectas

            except Exception as e:
                logger.error(f"[Email] Error en envío (intento {intento}/{self.max_retries}): {e}")
                if intento < self.max_retries:
                    time.sleep(2 ** intento)

        logger.error(f"[Email] No se pudo enviar tras {self.max_retries} intentos: {subject}")
