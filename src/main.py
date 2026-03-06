import os
import sys
import logging
import yaml
import signal
import socket

from core.logger import setup_logger
from audio.audio_buffer import AudioBuffer
from api.stt_processor import STTProcessor
from filters.keyword_filter import KeywordFilter
from integrations.telegram_bot import TelegramBot
from core.database import Database
from core.scan_config import scan_config
from pei.pei_motorola import MotorolaPEI
from streaming.ffmpeg_streamer import AudioStreamer
from pei.pei_daemon import PEIDaemon

# ---------------------------
# Logger y Banner
# ---------------------------
setup_logger()
logger = logging.getLogger(__name__)

print()
print("░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░░░░░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄")
print("░░█░░█▀▀░░█░░█▀▄░█▀█░▄▄▄░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄")
print("░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░░░░░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀")
print("2026 © Lluis de la Rubia / LluisAsturies")
print()

# ---------------------------
# Definir rutas del proyecto
# ---------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
KEYWORDS_PATH = os.path.join(PROJECT_ROOT, "config", "keywords.yaml")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
AUDIO_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "audio_output")

# ---------------------------
# Cargar configuración
# ---------------------------
try:
    with open(CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f)
    logger.info("Configuración cargada correctamente")
except FileNotFoundError:
    logger.critical(f"No se encontró config.yaml en {CONFIG_PATH}")
    print(f"ERROR: config.yaml no encontrado en {CONFIG_PATH}")
    sys.exit(1)
except yaml.YAMLError as e:
    logger.critical(f"Error parseando config.yaml: {e}")
    print(f"ERROR: config.yaml contiene errores de sintaxis YAML")
    sys.exit(1)

# ---------------------------
# Inicializar componentes
# ---------------------------
db = Database(**cfg["database"])
bot = TelegramBot(cfg["telegram"]["token"], cfg["telegram"]["chat_id"])

# Intentar inicializar AudioBuffer
audio_buffer = None
try:
    audio_buffer = AudioBuffer(
        device_index=cfg["audio"].get("device_index", None),
        sample_rate=cfg["audio"]["sample_rate"],
        channels=cfg["audio"]["channels"],
        prebuffer_seconds=cfg["audio"]["prebuffer_seconds"],
        output_dir=AUDIO_OUTPUT_DIR
    )
    logger.info("AudioBuffer inicializado correctamente")
except Exception as e:
    audio_buffer = None
    logger.critical(f"No se pudo inicializar AudioBuffer: {e}")
    print("ERROR: No se detectó micrófono disponible. Conecta un micrófono para procesar llamadas.")
    sys.exit(1)

stt = STTProcessor(
    model_name=cfg["stt"]["model"],
    language=cfg["stt"]["language"]
)

kf = KeywordFilter(KEYWORDS_PATH)

# ---------------------------
# Inicializar PEI Daemon
# ---------------------------
pei_daemon = PEIDaemon(
    motorola_pei_cls=MotorolaPEI,
    audio_buffer=audio_buffer,
    stt_processor=stt,
    keyword_filter=kf,
    db=db,
    bot=bot,
    port=cfg["pei"].get("port", ""),  # vacío = detección automática
    baudrate=cfg["pei"]["baudrate"]
)

# ---------------------------
# Inicializar AudioStreamer solo si habilitado
# ---------------------------
streamer = None
if cfg.get("streaming", {}).get("enabled") and audio_buffer:
    rtmp_url = cfg["streaming"].get("rtmp_url")
    if rtmp_url:
        host_port = rtmp_url.replace("rtmp://", "").split("/")[0]
        if ":" in host_port:
            host, port = host_port.split(":")
            port = int(port)
        else:
            host = host_port
            port = 1935
        # Comprobar conexión al servidor RTMP
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(2)
            s.connect((host, port))
            s.close()
            try:
                streamer = AudioStreamer()
                streamer.start()
                logger.info("Streaming activado")
            except Exception as e:
                streamer = None
                logger.warning(f"No se pudo iniciar AudioStreamer: {e}")
                print("ADVERTENCIA: Streaming no disponible. Se seguirá grabando localmente.")
        except Exception:
            logger.warning(f"No se puede conectar al servidor RTMP {rtmp_url}. Streaming deshabilitado.")
            print(f"ADVERTENCIA: No se puede conectar al servidor RTMP {rtmp_url}. Streaming deshabilitado.")
    else:
        logger.warning("RTMP URL no definida en config.yaml. Streaming deshabilitado.")
        print("ADVERTENCIA: RTMP URL no definida. Streaming deshabilitado.")

# ---------------------------
# Manejo de Ctrl+C y SIGTERM
# ---------------------------
def signal_handler(sig, frame):
    logger.info("Señal de interrupción recibida, cerrando aplicación...")
    pei_daemon.shutdown(streamer)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# ---------------------------
# Entrar en modo escucha PEI
# ---------------------------
logger.info("Iniciando PEI daemon con streaming (si está disponible)")

try:
    pei_daemon.escuchar_pei(streamer)
except RuntimeError as e:
    # Mensaje limpio sin traceback
    logger.critical(str(e))
    print(f"\nERROR CRÍTICO: {e}\nEl programa no puede continuar sin AudioBuffer.\n")
    sys.exit(1)
except KeyboardInterrupt:
    logger.info("Interrupción manual recibida, cerrando...")
    pei_daemon.shutdown(streamer)
    sys.exit(0)