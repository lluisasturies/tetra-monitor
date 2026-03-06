import os
import serial
import threading
import time
import yaml
from datetime import datetime
from typing import List
import glob

from audio_buffer import AudioBuffer
from stt_processor import STTProcessor
from keyword_filter import KeywordFilter
from telegram_bot import TelegramBot
from database import Database
from scan_config import scan_config
from pei_motorola import MotorolaPEI

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
keywords_path = os.path.join(base_dir, "../config/keywords.yaml")
kf = KeywordFilter(keywords_path)

# ---------------------------
# Mensaje de bienvenida
# ---------------------------
print()
print("░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░░░░░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄")
print("░░█░░█▀▀░░█░░█▀▄░█▀█░▄▄▄░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄")
print("░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░░░░░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀")
print("2026 © Lluis de la Rubia / LluisAsturies")
print("[INFO] Iniciando TETRA Monitor")

# ---------------------------
# Función para detectar puerto PEI automáticamente
# ---------------------------
def detectar_puerto_pei(port_config: str):
    # Primero, intentar usar el puerto especificado en config.yaml
    if port_config and os.path.exists(port_config):
        print(f"[INFO] Usando puerto especificado: {port_config}")
        return port_config

    # Si no existe, buscar automáticamente dispositivos serie
    posibles_puertos = glob.glob("/dev/ttyUSB*") + glob.glob("/dev/ttyACM*")
    if posibles_puertos:
        puerto = posibles_puertos[0]
        print(f"[INFO] Puerto especificado no encontrado. Detectado automáticamente: {puerto}")
        return puerto

    # Ningún puerto encontrado
    print("[ERROR] No se detectó ningún dispositivo Motorola PEI conectado.")
    print("Por favor, conecta el dispositivo y vuelve a ejecutar el programa.")
    return None

# ---------------------------
# Inicialización de radio PEI
# ---------------------------
port_detected = detectar_puerto_pei(cfg["pei"]["port"])
if port_detected is None:
    exit(1)  # Salida limpia si no hay dispositivo

radio = MotorolaPEI(port_detected, cfg["pei"]["baudrate"])

# ---------------------------
# Funciones de control del PEI
# ---------------------------
def follow_gssi(gssi: str):
    print(f"[PEI] Afiliando a GSSI: {gssi}")
    radio.set_active_gssi(str(gssi))

def follow_scanList(scan_list: str):
    print(f"[PEI] Cambiando a Scan List: {scan_list}")
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
    port = port_detected
    baudrate = cfg["pei"]["baudrate"]

    print(f"[INFO] Inicializando RadioPEI en {port}")

    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"[INFO] Conectado a PEI en {port} a {baudrate} bps")
    except serial.SerialException:
        print(f"[ERROR] No se pudo conectar al PEI en {port}. Verifica el dispositivo y los permisos.")
        return

    audio_buffer.start_buffer()

    while True:
        try:
            frame = ser.readline()
            if not frame:
                continue
            line = frame.decode(errors="ignore").strip()
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
# Inicio del daemon
# ---------------------------
if __name__ == "__main__":
    follow_gssi(scan_config.gssi)
    follow_scanList(scan_config.scan_list)
    escuchar_pei()