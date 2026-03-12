import time
import requests
from core.logger import logger


class TelegramBot:
    """Notificaciones Telegram para eventos operativos (llamadas, afiliacion)."""

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

        _a = alerts or {}
        self._alert_relevant_calls     = _a.get("relevant_calls",     True)
        self._alert_afiliacion_changed = _a.get("afiliacion_changed", True)

    # ------------------------------------------------------------------
    # Alertas operativas
    # ------------------------------------------------------------------

    def enviar_alerta(self, grupo: int, ssi: int, texto: str):
        """Notifica una llamada con keyword detectada."""
        if not self.enabled:
            logger.debug("[Telegram] Alerta ignorada -- Telegram desactivado en config")
            return
        if not self._alert_relevant_calls:
            logger.debug("[Telegram] Alerta de llamada ignorada -- relevant_calls desactivado")
            return
        if not self.radio_active:
            logger.debug("[Telegram] Alerta ignorada -- radio no conectada")
            return

        mensaje = (
            f"\U0001f6a8 *Alerta TETRA*\n"
            f"Grupo: `{grupo}`\n"
            f"SSI: `{ssi}`\n"
            f"Transcripcion: _{texto}_"
        )
        self._send_with_retry(mensaje)

    def notificar_cambio_afiliacion(self, tipo: str, anterior: str | None, nuevo: str | None):
        """Notifica un cambio de GSSI o scan list."""
        if not self.enabled or not self._alert_afiliacion_changed:
            return
        anterior_str = anterior or "(ninguna)"
        nuevo_str    = nuevo    or "(ninguna)"
        mensaje = (
            f"\U0001f4e1 *Cambio de afiliacion*\n"
            f"Tipo: `{tipo}`\n"
            f"Anterior: `{anterior_str}`\n"
            f"Nuevo: `{nuevo_str}`"
        )
        logger.info(f"[Telegram] Notificando cambio de {tipo}: '{anterior_str}' -> '{nuevo_str}'")
        self._send_with_retry(mensaje)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _send_with_retry(self, mensaje: str):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        for intento in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    url,
                    json={"chat_id": self.chat_id, "text": mensaje, "parse_mode": "Markdown"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    logger.info("[Telegram] Mensaje enviado correctamente")
                    return
                logger.warning(f"[Telegram] Respuesta {resp.status_code} (intento {intento})")
            except requests.exceptions.RequestException as e:
                logger.error(f"[Telegram] Error en envio (intento {intento}): {e}")
            # FIX: solo esperar si quedan mas intentos para no bloquear
            # innecesariamente despues del ultimo fallo.
            if intento < self.max_retries:
                time.sleep(2 ** intento)
        logger.error("[Telegram] No se pudo enviar el mensaje tras todos los reintentos")
