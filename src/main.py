import os
import logging
import yaml
import signal
import sys

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

audio_buffer = AudioBuffer(
    device_index=cfg["audio"]["device_index"],
    sample_rate=cfg["audio"]["sample_rate"],
    channels=cfg["audio"]["channels"],
    prebuffer_seconds=cfg["audio"]["prebuffer_seconds"],
    output_dir=cfg["audio"]["output_dir"]
)

stt = STTProcessor(
    model_name=cfg["stt"]["model"],
    language=cfg["stt"]["language"]
)

kf = KeywordFilter(os.path.join(base_dir, "../config/keywords.yaml"))

# ---------------------------
# Inicializar Motorola PEI
# ---------------------------
port = cfg["pei"]["port"]
baudrate = cfg["pei"]["baudrate"]
radio = MotorolaPEI(port, baudrate)

# ---------------------------
# Inicializar PEI Daemon
# ---------------------------
pei_daemon = PEIDaemon(
    motorola_pei=radio,
    audio_buffer=audio_buffer,
    stt_processor=stt,
    keyword_filter=kf,
    db=db,
    bot=bot,
    port=port,
    baudrate=baudrate
)

# ---------------------------
# Inicializar AudioStreamer solo si se habilita
# ---------------------------
streamer = None
if cfg.get("streaming", {}).get("enabled"):
    # Primero arranca el PEI daemon y luego inicializa streaming
    streamer = AudioStreamer()
    streamer.start()
    logger.info("Streaming activado")

# ---------------------------
# Manejo de Ctrl+C
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
logger.info("Iniciando PEI daemon con streaming")
pei_daemon.escuchar_pei(streamer)