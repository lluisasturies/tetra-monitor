import time
import requests
from core.logger import logger


class TelegramBot:
    def __init__(
        self,
        token: str,
        chat_id: str,
        max_retries: int = 3,
        enabled: bool = True,
        alerts: dict | None = None,
    ):
        self.token = token
        self.chat_id = chat_id
        self.max_retries = max_retries
        self.enabled = enabled
        self.radio_active = False

        # Flags de alertas de sistema — todos activos por defecto
        _a = alerts or {}
        self._alert_startup            = _a.get("startup",            True)
        self._alert_shutdown           = _a.get("shutdown",           True)
        self._alert_radio_connected    = _a.get("radio_connected",    True)
        self._alert_radio_disconnected = _a.get("radio_disconnected", True)
        self._alert_afiliacion_changed = _a.get("afiliacion_changed", True)

    # ------------------------------------------------------------------
    # Alertas de llamada
    # ------------------------------------------------------------------

    def enviar_alerta(self, grupo: int, ssi: int, texto: str):
        if not self.enabled:
            logger.debug("[Telegram] Alerta ignorada — Telegram desactivado en config")
            return
        if not self.radio_active:
            logger.debug("[Telegram] Alerta ignorada — radio no conectada")
            return

        mensaje = (
            f"\U0001f6a8 *Alerta TETRA*\n"
            f"Grupo: `{grupo}`\n"
            f"SSI: `{ssi}`\n"
            f"Transcripción: _{texto}_"
        )
        self._send_with_retry(mensaje)

    # ------------------------------------------------------------------
    # Alertas de sistema
    # ------------------------------------------------------------------

    def notificar_startup(self):
        if not self._alert_startup:
            return
        self._send_system("\U0001f7e2 *TETRA Monitor iniciado*\nSistema operativo y escuchando.")

    def notificar_shutdown(self):
        if not self._alert_shutdown:
            return
        self._send_system("\U0001f534 *TETRA Monitor detenido*\nEl sistema se ha cerrado correctamente.")

    def notificar_radio_conectada(self):
        if not self._alert_radio_connected:
            return
        self._send_system("\U0001f4f6 *Radio conectada*\nConexión PEI establecida correctamente.")

    def notificar_radio_desconectada(self):
        if not self._alert_radio_disconnected:
            return
        self._send_system("\u26a0\ufe0f *Radio desconectada*\nSe ha perdido la conexión con el PEI. Intentando reconectar...")

    def notificar_cambio_afiliacion(self, tipo: str, anterior: str | None, nuevo: str | None):
        if not self._alert_afiliacion_changed:
            return
        anterior_str = anterior or "(ninguna)"
        nuevo_str    = nuevo    or "(ninguna)"
        mensaje = (
            f"\U0001f4e1 *Cambio de afiliación*\n"
            f"Tipo: `{tipo}`\n"
            f"Anterior: `{anterior_str}`\n"
            f"Nuevo: `{nuevo_str}`"
        )
        logger.info(f"[Telegram] Notificando cambio de {tipo}: '{anterior_str}' -> '{nuevo_str}'")
        self._send_with_retry(mensaje)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _send_system(self, mensaje: str):
        """Envía una notificación de sistema (no requiere radio activa)."""
        if not self.enabled:
            logger.debug("[Telegram] Notificación de sistema ignorada — Telegram desactivado")
            return
        logger.info(f"[Telegram] Notificación de sistema: {mensaje[:60].strip()}...")
        self._send_with_retry(mensaje)

    def _send_with_retry(self, mensaje: str):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        for intento in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json={
                        "chat_id": self.chat_id,
                        "text": mensaje,
                        "parse_mode": "Markdown"
                    },
                    timeout=10
                )
                if resp.status_code == 200:
                    logger.info("Mensaje Telegram enviado correctamente")
                    return
                else:
                    logger.warning(f"Telegram respondió {resp.status_code} (intento {intento})")
            except requests.exceptions.RequestException as e:
                logger.error(f"Error enviando Telegram (intento {intento}): {e}")

            time.sleep(2 ** intento)

        logger.error("No se pudo enviar el mensaje por Telegram tras todos los reintentos")
