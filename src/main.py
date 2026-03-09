import os
import sys
import yaml
import signal
from dotenv import load_dotenv

# Cargar variables de entorno antes que nada
load_dotenv()

from core.logger import logger
from audio.audio_buffer import AudioBuffer
from core.stt_processor import STTProcessor
from filters.keyword_filter import KeywordFilter
from integrations.telegram_bot import TelegramBot
from core.database import Database
from pei.hardware.pei_motorola import MotorolaPEI
from pei.daemon.pei_daemon import PEIDaemon
from streaming import create_streamer

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

# ---------------------------
# Cargar configuración
# ---------------------------
try:
    with open(CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f)
    logger.info("Configuración cargada correctamente")
except FileNotFoundError:
    logger.critical(f"No se encontró config.yaml en {CONFIG_PATH}")
    sys.exit(1)
except yaml.YAMLError as e:
    logger.critical(f"Error parseando config.yaml: {e}")
    sys.exit(1)

AUDIO_OUTPUT_DIR = os.path.join(PROJECT_ROOT, cfg["audio"].get("output_dir", "data/audio"))
RETENTION_DAYS = cfg["audio"].get("retention_days", 7)

# Leer flags de activación
RECORDING_ENABLED  = cfg["audio"].get("recording_enabled", True)
PROCESSING_ENABLED = cfg["pei"].get("processing_enabled", True)
TELEGRAM_ENABLED   = cfg["telegram"].get("enabled", True)

# Sobreescribir credenciales con variables de entorno (tienen prioridad)
cfg["database"]["password"] = os.getenv("DB_PASSWORD", cfg["database"].get("password", ""))
cfg["database"]["user"]     = os.getenv("DB_USER", cfg["database"].get("user", ""))
cfg["telegram"]["token"]    = os.getenv("TELEGRAM_TOKEN", cfg["telegram"].get("token", ""))
cfg["telegram"]["chat_id"]  = os.getenv("TELEGRAM_CHAT_ID", cfg["telegram"].get("chat_id", ""))
cfg["api"]["jwt_secret"]    = os.getenv("JWT_SECRET", cfg["api"].get("jwt_secret", ""))

# ---------------------------
# Inicializar componentes
# ---------------------------
db = Database(**cfg["database"])
bot = TelegramBot(
    cfg["telegram"]["token"],
    cfg["telegram"]["chat_id"],
    enabled=TELEGRAM_ENABLED
)

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
    logger.critical(f"No se pudo inicializar AudioBuffer: {e}")
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
    port=cfg["pei"].get("port", ""),
    baudrate=cfg["pei"]["baudrate"],
    audio_output_dir=AUDIO_OUTPUT_DIR,
    retention_days=RETENTION_DAYS,
    recording_enabled=RECORDING_ENABLED,
    processing_enabled=PROCESSING_ENABLED,
)

# ---------------------------
# Inicializar Streaming
# ---------------------------
streamer = None
stream_cfg = cfg.get("streaming", {})

if stream_cfg.get("enabled", False):
    streamer = create_streamer(stream_cfg)
    if streamer:
        logger.info(f"Streaming inicializado correctamente ({streamer.__class__.__name__})")
    else:
        logger.info("Streaming habilitado pero no se encontró URL válida")
else:
    logger.info("Streaming deshabilitado en config.yaml")

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
# Ejecutar PEI Daemon
# ---------------------------
logger.info("Iniciando PEI con streaming")

try:
    pei_daemon.escuchar_pei(streamer)
except RuntimeError as e:
    logger.critical(f"Error en PEI: {e}")
    sys.exit(1)
except KeyboardInterrupt:
    logger.info("Interrupción por teclado recibida")
    pei_daemon.shutdown(streamer)
    sys.exit(0)