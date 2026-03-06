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
from pei.pei_motorola import MotorolaPEI
from pei.pei_daemon import PEIDaemon

from streaming.rtmp_streamer import RTMPStreamer
from streaming.icecast_streamer import IcecastStreamer

# ---------------------------
# Logger y Banner
# ---------------------------
setup_logger()
logger = logging.getLogger(__name__)

print()
print("░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░░░░░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄")
print("░░█░░█▀▀░░█░░█▀▄░█▀█░▄▄▄░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄")
print("░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░░░░░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀")
print("2026 © Lluis de la Rubia / LluisAsturies\n")

# ---------------------------
# Definir rutas del proyecto
# ---------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "config.yaml")
KEYWORDS_PATH = os.path.join(PROJECT_ROOT, "config", "keywords.yaml")
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
# Inicializar Streaming
# ---------------------------
streamer = None
if cfg.get("streaming", {}).get("enabled") and audio_buffer:
    rtmp_url = cfg["streaming"].get("rtmp_url")
    icecast_url = cfg["streaming"].get("icecast_url")

    if rtmp_url:
        streamer = RTMPStreamer(rtmp_url, cfg["audio"]["sample_rate"], cfg["audio"]["channels"])

    elif icecast_url:
        streamer = IcecastStreamer(icecast_url, cfg["audio"]["sample_rate"], cfg["audio"]["channels"])

    else:
        logger.warning("No se definió RTMP ni Icecast en config.yaml. Streaming deshabilitado.")

    # Comprobar conexión al servidor
    if streamer:
        host_port = streamer.url.replace("http://","").replace("https://","").replace("rtmp://","").split("/")[0]

        if ":" in host_port:
            host, port = host_port.split(":")
            port = int(port)

        else:
            host = host_port
            port = 1935 if isinstance(streamer, RTMPStreamer) else 8000
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            s.settimeout(2)
            s.connect((host, port))
            s.close()

            try:
                streamer.start()

            except Exception as e:
                logger.warning(f"No se pudo iniciar el streamer: {e}")

        except Exception:
            logger.warning(f"No se puede conectar al servidor {streamer.url}. Streaming deshabilitado.")

# ---------------------------
# Manejo de señales
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

try:
    pei_daemon.escuchar_pei(streamer)

except RuntimeError as e:
    logger.critical(str(e))
    print(f"\nERROR CRÍTICO: {e}\nNo se pueden procesar llamadas sin micrófono.\n")
    sys.exit(1)

except KeyboardInterrupt:
    pei_daemon.shutdown(streamer)
    sys.exit(0)