import serial
import threading
import time
import os
import yaml
from datetime import datetime

from audio_buffer import AudioBuffer
from stt_processor import STTProcessor
from keyword_filter import KeywordFilter
from telegram_bot import TelegramBot
from database import Database

# ---------------------------
# Cargar configuración
# ---------------------------
with open("config/config.yaml", "r") as f:
    cfg = yaml.safe_load(f)

# Inicializar módulos
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
kf = KeywordFilter(cfg["keywords"])

# ---------------------------
# Función para manejar evento de llamada
# ---------------------------
def procesar_llamada(grupo, ssi):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"evento_{grupo}_{ssi}_{timestamp}.flac"

    # Iniciar grabación con pre-buffer
    audio_buffer.start_recording()
    print(f"[{timestamp}] Grabando llamada Grupo:{grupo} SSI:{ssi}")

    # Esperar duración de la transmisión (o PTT detectado por PEI)
    # Para producción, se puede usar evento CALL_END real
    while audio_buffer.recording:
        time.sleep(0.5)  # Ajustable según frecuencia de chequeo

    # Guardar audio
    path_audio = audio_buffer.stop_recording(filename)
    print(f"[{timestamp}] Audio guardado: {path_audio}")

    # Transcribir
    texto = stt.transcribir(path_audio)
    print(f"[{timestamp}] Transcripción: {texto}")

    # Filtrar palabras clave
    if kf.contiene_evento(texto):
        db.guardar_evento(grupo, ssi, texto, path_audio)
        bot.enviar_alerta(grupo, ssi, texto)
        print(f"[{timestamp}] Evento relevante detectado y notificado")
    else:
        print(f"[{timestamp}] No se detectaron palabras clave, audio descartado")

# ---------------------------
# PEI Listener
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

    audio_buffer.start_buffer()  # Inicia buffer de audio siempre activo

    while True:
        try:
            frame = ser.readline()
            if not frame:
                continue
            # Aquí parsear frame PEI real de Motorola
            # Ejemplo de simulación de parsing
            # frame esperado: b"CALL_START;grupo;ssi\n"
            try:
                line = frame.decode().strip()
                if line.startswith("CALL_START"):
                    _, grupo_str, ssi_str = line.split(";")
                    grupo = int(grupo_str)
                    ssi = int(ssi_str)
                    threading.Thread(target=procesar_llamada, args=(grupo, ssi)).start()
                elif line.startswith("CALL_END"):
                    # Se puede usar para parar grabación si se quiere
                    audio_buffer.recording = False
            except Exception as parse_error:
                print(f"[WARN] No se pudo parsear frame: {frame} -> {parse_error}")

        except Exception as e:
            print(f"[ERROR] PEI listener: {e}")
            time.sleep(1)

# ---------------------------
# Inicio principal
# ---------------------------
if __name__ == "__main__":
    print("[INFO] Iniciando demonio TETRA Monitor producción")
    escuchar_pei()