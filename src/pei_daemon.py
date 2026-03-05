import os
import serial
import threading
import time
import yaml
from datetime import datetime
from typing import List

from audio_buffer import AudioBuffer
from stt_processor import STTProcessor
from keyword_filter import KeywordFilter
from telegram_bot import TelegramBot
from database import Database
from scan_config import scan_config

# ---------------------------
# Cargar configuración principal
# ---------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, "../config/config.yaml")

with open(config_path, "r") as f:
    cfg = yaml.safe_load(f)

db = Database(**cfg["database"])
bot = TelegramBot(cfg["telegram"]["token"], cfg["telegram"]["chat_id"])
audio_buffer = AudioBuffer(
    device_index=cfg["audio"]["device_index"],
    sample_rate=cfg["audio"]["sample_rate"],
    channels=cfg["audio"]["channels"],
    prebuffer_seconds=cfg["audio"]["prebuffer_seconds"],
    output_dir=cfg["audio"]["output_dir"]
)
stt = STTProcessor(model_name=cfg["stt"]["model"], language=cfg["stt"]["language"])
kf = KeywordFilter("config/keywords.yaml")

# ---------------------------
# PEI Radio Controller genérico
# ---------------------------
class RadioPEI:
    def __init__(self, port="/dev/ttyUSB0"):
        self.port = port
        print(f"[INFO] RadioPEI inicializada en {port}")

    def set_active_gssi(self, gssi: str):
        print(f"[PEI] Cambiando GSSI activo a {gssi}")

    def set_scan_list(self, scan_list: str):
        print(f"[PEI] Actualizando Scan List: {scan_list}")

radio = RadioPEI(port=cfg["pei"]["port"])

def aplicar_config_radio():
    """Función pública para que api.py aplique cambios a la radio"""
    radio.set_active_gssi(scan_config.gssi)
    radio.set_scan_list(scan_config.scan_list)

# ---------------------------
# Función para procesar llamada
# ---------------------------
def procesar_llamada(grupo, ssi):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"evento_{grupo}_{ssi}_{timestamp}.flac"

    audio_buffer.start_recording()
    print(f"[{timestamp}] Grabando llamada Grupo:{grupo} SSI:{ssi}")

    while audio_buffer.recording:
        time.sleep(0.5)

    path_audio = audio_buffer.stop_recording(filename)
    print(f"[{timestamp}] Audio guardado: {path_audio}")

    texto = stt.transcribir(path_audio)
    print(f"[{timestamp}] Transcripción: {texto}")

    if kf.contiene_evento(texto):
        db.guardar_evento(grupo, ssi, texto, path_audio)
        bot.enviar_alerta(grupo, ssi, texto)
        print(f"[{timestamp}] Evento relevante detectado y notificado")
    else:
        print(f"[{timestamp}] No se detectaron palabras clave, audio descartado")

# ---------------------------
# Listener PEI
# ---------------------------
def escuchar_pei():
    port = cfg["pei"]["port"]
    baudrate = cfg["pei"]["baudrate"]

    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"[INFO] Conectado a PEI en {port} a {baudrate} bps")
    except Exception as e:
        print(f"[ERROR] No se pudo conectar al PEI: {e}")
        return

    audio_buffer.start_buffer()

    while True:
        try:
            frame = ser.readline()
            if not frame:
                continue
            line = frame.decode().strip()
            if line.startswith("CALL_START"):
                _, grupo_str, ssi_str = line.split(";")
                grupo = int(grupo_str)
                ssi = int(ssi_str)

                threading.Thread(target=procesar_llamada, args=(grupo, ssi)).start()
            elif line.startswith("CALL_END"):
                audio_buffer.recording = False

        except Exception as e:
            print(f"[ERROR] PEI listener: {e}")
            time.sleep(1)

# ---------------------------
# Inicio principal
# ---------------------------
if __name__ == "__main__":
    cabecera = """
    ░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄
    ░░█░░█▀▀░░█░░█▀▄░█▀█░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄
    ░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀
    """
    print(cabecera)
    print("[INFO] Iniciando TETRA Monitor producción")
    aplicar_config_radio()
    escuchar_pei()