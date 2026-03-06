import os
import logging
import yaml
import signal
import sys
import socket
import sounddevice as sd

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
# Cargar configuración
# ---------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, "../config/config.yaml")

with open(config_path, "r") as f:
    cfg = yaml.safe_load(f)
logger.info("Configuración cargada correctamente")

# ---------------------------
# Inicializar componentes
# ---------------------------
db = Database(**cfg["database"])
bot = TelegramBot(cfg["telegram"]["token"], cfg["telegram"]["chat_id"])

# Intentar inicializar AudioBuffer
audio_buffer = None
try:
    audio_buffer = AudioBuffer(
        device_index=cfg["audio"]["device_index"],
        sample_rate=cfg["audio"]["sample_rate"],
        channels=cfg["audio"]["channels"],
        prebuffer_seconds=cfg["audio"]["prebuffer_seconds"],
        output_dir=cfg["audio"]["output_dir"]
    )
    logger.info("AudioBuffer inicializado correctamente")
except Exception as e:
    logger.warning(f"No se pudo inicializar AudioBuffer: {e}")

stt = STTProcessor(
    model_name=cfg["stt"]["model"],
    language=cfg["stt"]["language"]
)

kf = KeywordFilter(os.path.join(base_dir, "../config/keywords.yaml"))

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
# Inicializar AudioStreamer solo si habilitado y RTMP disponible
# ---------------------------
streamer = None
if cfg.get("streaming", {}).get("enabled") and audio_buffer:
    rtmp_url = cfg["streaming"].get("rtmp_url")
    if rtmp_url:
        # Comprobar conexión RTMP
        host, port = rtmp_url.replace("rtmp://","").split("/")[0].split(":") if ":" in rtmp_url else (rtmp_url.split("/")[0], 1935)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(2)
            s.connect((host, int(port)))
            s.close()
            # Inicializar streamer
            try:
                streamer = AudioStreamer()
                streamer.start()
                logger.info("Streaming activado")
            except Exception as e:
                logger.warning(f"No se pudo iniciar AudioStreamer: {e}")
        except Exception:
            logger.warning(f"No se puede conectar al servidor RTMP {rtmp_url}. Streaming deshabilitado.")
    else:
        logger.warning("RTMP URL no definida en config.yaml. Streaming deshabilitado.")
else:
    if not cfg.get("streaming", {}).get("enabled"):
        logger.info("Streaming deshabilitado en config.yaml")
    else:
        logger.warning("AudioBuffer no inicializado. Streaming deshabilitado.")

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
pei_daemon.escuchar_pei(streamer)