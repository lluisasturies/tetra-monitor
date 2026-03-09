import os
import sys
import yaml
import signal
import threading
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from core.logger import logger, set_level
from core.scan_config import ScanConfig
from audio.audio_buffer import AudioBuffer
from core.stt_processor import STTProcessor
from filters.keyword_filter import KeywordFilter
from integrations.telegram_bot import TelegramBot
from db.pool import DBPool
from db.llamadas import LlamadasDB
from pei.hardware.pei_motorola import MotorolaPEI
from pei.daemon.pei_daemon import PEIDaemon
from streaming import create_streamer
from app_state import app_state
from api.api import app

print()
print("░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░░░░░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄")
print("░░█░░█▀▀░░█░░█▀▄░█▀█░▄▄▄░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄")
print("░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░░░░░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀")
print("2026 © Lluis de la Rubia / LluisAsturies")
print()

# ---------------------------
# Definir rutas del proyecto
# ---------------------------
PROJECT_ROOT  = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH   = os.path.join(PROJECT_ROOT, "config", "config.yaml")
KEYWORDS_PATH = os.path.join(PROJECT_ROOT, "config", "keywords.yaml")
SCAN_PATH     = os.path.join(PROJECT_ROOT, "config", "scan.yaml")

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

# Aplicar nivel de log desde config
set_level(cfg.get("logging", {}).get("level", "INFO"))

AUDIO_OUTPUT_DIR   = os.path.join(PROJECT_ROOT, cfg["audio"].get("output_dir", "data/audio"))
RETENTION_DAYS     = cfg["audio"].get("retention_days", 7)
RECORDING_ENABLED  = cfg["audio"].get("recording_enabled", True)
PROCESSING_ENABLED = cfg["pei"].get("processing_enabled", True)
TELEGRAM_ENABLED   = cfg["telegram"].get("enabled", True)

# ---------------------------
# Validar variables de entorno
# ---------------------------
_env_errors = []
if not os.getenv("DB_USER"):          _env_errors.append("DB_USER")
if not os.getenv("DB_PASSWORD"):      _env_errors.append("DB_PASSWORD")
if TELEGRAM_ENABLED and not os.getenv("TELEGRAM_TOKEN"):   _env_errors.append("TELEGRAM_TOKEN")
if TELEGRAM_ENABLED and not os.getenv("TELEGRAM_CHAT_ID"): _env_errors.append("TELEGRAM_CHAT_ID")
if not os.getenv("JWT_SECRET"):       _env_errors.append("JWT_SECRET")
if not os.getenv("API_USER"):         _env_errors.append("API_USER")
if not os.getenv("API_PASSWORD"):     _env_errors.append("API_PASSWORD")

if _env_errors:
    for var in _env_errors:
        logger.critical(f"Variable de entorno obligatoria no definida: {var}")
    sys.exit(1)

DB_USER          = os.getenv("DB_USER", "")
DB_PASSWORD      = os.getenv("DB_PASSWORD", "")
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ---------------------------
# Inicializar scan config
# ---------------------------
scan_config = ScanConfig(SCAN_PATH)
app_state.scan_config = scan_config

# ---------------------------
# Inicializar pool y repositorios
# ---------------------------
pool = DBPool(
    host=cfg["database"]["host"],
    port=cfg["database"]["port"],
    dbname=cfg["database"]["dbname"],
    user=DB_USER,
    password=DB_PASSWORD,
)
llamadas_db = LlamadasDB(pool)

app_state.pool     = pool
app_state.llamadas = llamadas_db

# ---------------------------
# Inicializar bot
# ---------------------------
bot = TelegramBot(
    token=TELEGRAM_TOKEN,
    chat_id=TELEGRAM_CHAT_ID,
    enabled=TELEGRAM_ENABLED,
)
app_state.bot = bot

# ---------------------------
# Inicializar AudioBuffer
# ---------------------------
def _is_hardware_error(msg: str) -> bool:
    msg = msg.lower()
    return any(k in msg for k in [
        "querying device", "ttyusb", "no such file", "puerto", "serial",
        "audiobuffer no disponible", "audiobuffer"
    ])

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
    if _is_hardware_error(str(e)):
        logger.warning(f"Dispositivo de audio no disponible: {e}")
        logger.warning("Revisa 'device_index' en config.yaml y vuelve a arrancar.")
        sys.exit(0)
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
    llamadas_db=llamadas_db,
    scan_config=scan_config,
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
    stream_cfg["samplerate"] = cfg["audio"]["sample_rate"]
    stream_cfg["channels"]   = cfg["audio"]["channels"]
    streamer = create_streamer(stream_cfg)
    if streamer:
        logger.info(f"Streaming inicializado correctamente ({streamer.__class__.__name__})")
    else:
        logger.info("Streaming habilitado pero no se encontró URL válida")
else:
    logger.info("Streaming deshabilitado en config.yaml")

# ---------------------------
# Arrancar API en hilo separado
# ---------------------------
def _run_api():
    uvicorn.run(
        app,
        host=cfg["api"]["host"],
        port=cfg["api"]["port"],
        log_level="warning"
    )

api_thread = threading.Thread(target=_run_api, daemon=True)
api_thread.start()
logger.info(f"API arrancada en {cfg['api']['host']}:{cfg['api']['port']}")

# ---------------------------
# Manejo de Ctrl+C y SIGTERM
# ---------------------------
def signal_handler(sig, frame):
    logger.info("Señal de interrupción recibida, cerrando aplicación...")
    pei_daemon.shutdown(streamer)
    pool.closeall()
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
    if _is_hardware_error(str(e)):
        logger.warning(f"Hardware no disponible: {e}")
        logger.warning("Conecta el hardware y vuelve a arrancar.")
        sys.exit(0)
    logger.critical(f"Error en PEI: {e}")
    sys.exit(1)
except KeyboardInterrupt:
    logger.info("Interrupción por teclado recibida")
    pei_daemon.shutdown(streamer)
    pool.closeall()
    sys.exit(0)
