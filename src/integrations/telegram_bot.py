import requests

class TelegramBot:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id

    def enviar_alerta(self, grupo, ssi, texto):
        mensaje = f"🚨 ALERTA TETRA\nGrupo: {grupo}\nSSI: {ssi}\nTexto: {texto}"
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        requests.post(url, data={"chat_id": self.chat_id, "text": mensaje})