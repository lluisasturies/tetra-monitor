import time
import requests
from core.logger import logger


class TelegramBot:
    def __init__(self, token: str, chat_id: str, max_retries: int = 3, enabled: bool = True):
        self.token = token
        self.chat_id = chat_id
        self.max_retries = max_retries
        self.enabled = enabled
        self.radio_active = False

    def enviar_alerta(self, grupo: int, ssi: int, texto: str):
        if not self.enabled:
            logger.debug("[Telegram] Alerta ignorada — Telegram desactivado en config")
            return
        if not self.radio_active:
            logger.debug("[Telegram] Alerta ignorada — radio no conectada")
            return

        mensaje = (
            f"🚨 *Alerta TETRA*\n"
            f"Grupo: `{grupo}`\n"
            f"SSI: `{ssi}`\n"
            f"Transcripción: _{texto}_"
        )
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
                    logger.info("Alerta Telegram enviada correctamente")
                    return
                else:
                    logger.warning(f"Telegram respondió {resp.status_code} (intento {intento})")
            except requests.exceptions.RequestException as e:
                logger.error(f"Error enviando Telegram (intento {intento}): {e}")

            time.sleep(2 ** intento)

        logger.error("No se pudo enviar la alerta por Telegram tras todos los reintentos")
