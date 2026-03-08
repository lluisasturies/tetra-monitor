import time
import requests
from core.logger import logger

class TelegramBot:
    def __init__(self, token: str, chat_id: str, max_retries: int = 3):
        self.token = token
        self.chat_id = chat_id
        self.max_retries = max_retries
        self.base_url = f"https://api.telegram.org/bot{token}"

    def enviar_alerta(self, grupo: int, ssi: int, texto: str):
        mensaje = (
            f"🚨 *Alerta TETRA*\n"
            f"Grupo: `{grupo}`\n"
            f"SSI: `{ssi}`\n"
            f"Transcripción: _{texto}_"
        )
        self._send_with_retry(mensaje)

    def _send_with_retry(self, mensaje: str):
        for intento in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    f"{self.base_url}/sendMessage",
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

            time.sleep(2 ** intento)  # backoff exponencial: 2s, 4s, 8s

        logger.error("No se pudo enviar la alerta por Telegram tras todos los reintentos")