import requests
from core.logger import logger


class TelegramBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id

    def enviar_alerta(self, grupo: int, ssi: int, texto: str) -> bool:
        mensaje = f"🚨 ALERTA TETRA\nGrupo: {grupo}\nSSI: {ssi}\nTexto: {texto}"
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        try:
            r = requests.post(
                url,
                data={"chat_id": self.chat_id, "text": mensaje},
                timeout=10
            )
            r.raise_for_status()
            logger.info(f"Alerta Telegram enviada — Grupo {grupo}, SSI {ssi}")
            return True
        except requests.RequestException as e:
            logger.error(f"Error enviando alerta Telegram: {e}")
            return False
