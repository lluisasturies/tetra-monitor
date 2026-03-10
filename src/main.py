import os
import sys
import yaml
import signal
import threading
import uvicorn
from dotenv import load_dotenv

load_dotenv()

from core.logger import logger, set_level  # noqa: E402
from core.afiliacion import AfiliacionConfig  # noqa: E402
from audio.audio_buffer import AudioBuffer  # noqa: E402
from core.stt_processor import STTProcessor  # noqa: E402
from filters.keyword_filter import KeywordFilter  # noqa: E402
from integrations.telegram_bot import TelegramBot  # noqa: E402
from db.pool import DBPool  # noqa: E402
from db.llamadas import LlamadasDB  # noqa: E402
from db.grupos import GruposDB  # noqa: E402
from pei.hardware.pei_motorola import MotorolaPEI  # noqa: E402
from pei.daemon.pei_daemon import PEIDaemon  # noqa: E402
from streaming import create_streamer  # noqa: E402
from app_state import app_state  # noqa: E402

print()
print("░▀█▀░█▀▀░▀█▀░█▀▄░█▀▀░░░░░█▄█░█▀▀░█▀▀░▀█▀░▀█▀░█▀▀░█▀▄")
print("░░█░░█▀▀░░█░░█▀▄░█▀▀░▄▄▄░█░█░█░░░█░█░░█░░░█░░█░█░█▀▄")
print("░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░░░░░▀░▀░▀▀▀░▀▀▀░▀▀▀░░▀░░▀▀▀░▀░▀")
print("2026 © Lluis de la Rubia / LluisAsturies")
print()

PROJECT_ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH     = os.path.join(PROJECT_ROOT, "config", "config.yaml")
KEYWORDS_PATH   = os.path.join(PROJECT_ROOT, "config", "keywords.yaml")
AFILIACION_PATH = os.path.join(PROJECT_ROOT, "config", "afiliacion.yaml")
GRUPOS_PATH     = os.path.join(PROJECT_ROOT, "config", "grupos.yaml")


def _is_hardware_error(msg: str) -> bool:
    msg = msg.lower()
    return any(k in msg for k in [
        "querying device", "ttyusb", "no such file", "puerto", "serial",
        "audiobuffer no disponible", "audiobuffer"
    ])


def _load_config() -> dict:
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
    set_level(cfg.get("logging", {}).get("level", "INFO"))
    return cfg


def _validate_env(cfg: dict) -> dict:
    telegram_enabled = cfg["telegram"].get("enabled", True)
    errors = []
    if not os.getenv("DB_USER"):          errors.append("DB_USER")
    if not os.getenv("DB_PASSWORD"):      errors.append("DB_PASSWORD")
    if not os.getenv("JWT_SECRET"):       errors.append("JWT_SECRET")
    if not os.getenv("API_USER"):         errors.append("API_USER")
    if not os.getenv("API_PASSWORD_HASH"):
        if os.getenv("API_PASSWORD"):
            logger.critical("API_PASSWORD ya no se usa — ejecuta 'make set-password' para migrar a API_PASSWORD_HASH")
        else:
            errors.append("API_PASSWORD_HASH")
    if telegram_enabled:
        if not os.getenv("TELEGRAM_TOKEN"):   errors.append("TELEGRAM_TOKEN")
        if not os.getenv("TELEGRAM_CHAT_ID"): errors.append("TELEGRAM_CHAT_ID")
    if errors:
        for var in errors:
            logger.critical(f"Variable de entorno obligatoria no definida: {var}")
        sys.exit(1)
    return {
        "db_user":          os.getenv("DB_USER", ""),
        "db_password":      os.getenv("DB_PASSWORD", ""),
        "telegram_token":   os.getenv("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
    }


def _init_db(cfg: dict, env: dict) -> tuple[DBPool, LlamadasDB, GruposDB]:
    pool = DBPool(
        host=cfg["database"]["host"],
        port=cfg["database"]["port"],
        dbname=cfg["database"]["dbname"],
        user=env["db_user"],
        password=env["db_password"],
    )
    llamadas_db = LlamadasDB(pool)
    grupos_db   = GruposDB(pool)
    app_state.pool     = pool
    app_state.llamadas = llamadas_db
    app_state.grupos   = grupos_db
    grupos_db.seed_from_yaml(GRUPOS_PATH)
    return pool, llamadas_db, grupos_db


def _init_bot(cfg: dict, env: dict) -> TelegramBot:
    bot = TelegramBot(
        token=env["telegram_token"],
        chat_id=env["telegram_chat_id"],
        enabled=cfg["telegram"].get("enabled", True),
        alerts=cfg["telegram"].get("alerts", {}),
    )
    app_state.bot = bot
    return bot


def _init_audio(cfg: dict, audio_output_dir: str) -> tuple[AudioBuffer, STTProcessor, KeywordFilter]:
    try:
        audio_buffer = AudioBuffer(
            device_index=cfg["audio"].get("device_index", None),
            sample_rate=cfg["audio"]["sample_rate"],
            channels=cfg["audio"]["channels"],
            prebuffer_seconds=cfg["audio"]["prebuffer_seconds"],
            output_dir=audio_output_dir,
        )
    except Exception as e:
        if _is_hardware_error(str(e)):
            logger.warning(f"Dispositivo de audio no disponible: {e}")
            logger.warning("Revisa 'device_index' en config.yaml y vuelve a arrancar.")
            sys.exit(0)
        logger.critical(f"No se pudo inicializar AudioBuffer: {e}")
        sys.exit(1)
    stt = STTProcessor(model_name=cfg["stt"]["model"], language=cfg["stt"]["language"])
    kf  = KeywordFilter(KEYWORDS_PATH)
    app_state.keyword_filter = kf
    return audio_buffer, stt, kf


def _init_pei(
    cfg: dict, audio_buffer: AudioBuffer, stt: STTProcessor, kf: KeywordFilter,
    llamadas_db: LlamadasDB, afiliacion: AfiliacionConfig, bot: TelegramBot,
    audio_output_dir: str,
) -> PEIDaemon:
    return PEIDaemon(
        motorola_pei_cls=MotorolaPEI,
        audio_buffer=audio_buffer,
        stt_processor=stt,
        keyword_filter=kf,
        llamadas_db=llamadas_db,
        afiliacion=afiliacion,
        bot=bot,
        port=cfg["pei"].get("port", ""),
        baudrate=cfg["pei"]["baudrate"],
        audio_output_dir=audio_output_dir,
        retention_days=cfg["audio"].get("retention_days", 7),
        recording_enabled=cfg["audio"].get("recording_enabled", True),
        processing_enabled=cfg["pei"].get("processing_enabled", True),
        save_all_calls=cfg["database"].get("save_all_calls", False),
        watchdog_timeout=cfg["pei"].get("watchdog_timeout", 60),
        max_recording_seconds=cfg["audio"].get("max_recording_seconds", 120),
    )


def _init_api(cfg: dict) -> threading.Thread:
    try:
        from api.api import app
    except RuntimeError as e:
        logger.critical(f"Error al inicializar la API: {e}")
        sys.exit(1)
    def _run():
        uvicorn.run(app, host=cfg["api"]["host"], port=cfg["api"]["port"], log_level="warning")
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info(f"API arrancada en {cfg['api']['host']}:{cfg['api']['port']}")
    return thread


def _init_streaming(cfg: dict) -> object | None:
    stream_cfg = cfg.get("streaming", {})
    if not stream_cfg.get("enabled", False):
        app_state.streaming_active = False
        return None
    stream_cfg["samplerate"] = cfg["audio"]["sample_rate"]
    stream_cfg["channels"]   = cfg["audio"]["channels"]
    streamer = create_streamer(stream_cfg)
    app_state.streaming_active = streamer is not None and streamer.running
    return streamer


def main():
    cfg = _load_config()
    env = _validate_env(cfg)
    audio_output_dir = os.path.join(PROJECT_ROOT, cfg["audio"].get("output_dir", "data/audio"))

    afiliacion = AfiliacionConfig(AFILIACION_PATH)
    app_state.afiliacion = afiliacion

    pool, llamadas_db, grupos_db = _init_db(cfg, env)
    bot                          = _init_bot(cfg, env)
    afiliacion.set_bot(bot)
    audio_buffer, stt, kf        = _init_audio(cfg, audio_output_dir)
    pei_daemon                   = _init_pei(cfg, audio_buffer, stt, kf, llamadas_db, afiliacion, bot, audio_output_dir)

    streaming_enabled  = cfg.get("streaming", {}).get("enabled", False)
    recording_enabled  = cfg["audio"].get("recording_enabled", True)
    processing_enabled = cfg["pei"].get("processing_enabled", True)
    telegram_enabled   = cfg["telegram"].get("enabled", True)
    save_all_calls     = cfg["database"].get("save_all_calls", False)
    watchdog_timeout   = cfg["pei"].get("watchdog_timeout", 60)
    max_rec_seconds    = cfg["audio"].get("max_recording_seconds", 120)

    logger.info(f"Grabación de audio       : {'ACTIVADA'  if recording_enabled  else 'DESACTIVADA'}")
    logger.info(f"Procesado PEI            : {'ACTIVADO'  if processing_enabled else 'DESACTIVADO'}")
    logger.info(f"Notificaciones Telegram  : {'ACTIVADAS' if telegram_enabled   else 'DESACTIVADAS'}")
    logger.info(f"Streaming                : {'ACTIVADO'  if streaming_enabled  else 'DESACTIVADO'}")
    logger.info(f"Guardado en BD           : {'TODAS las llamadas' if save_all_calls else 'Solo llamadas con keyword'}")
    logger.info(f"Watchdog PEI             : {watchdog_timeout}s (0=desactivado)")
    logger.info(f"Límite grabación        : {max_rec_seconds}s (0=desactivado)")

    _init_api(cfg)
    streamer = _init_streaming(cfg)
    bot.notificar_startup()

    def _signal_handler(sig, frame):
        logger.info("Señal de interrupción recibida, cerrando aplicación...")
        bot.notificar_shutdown()
        app_state.streaming_active = False
        pei_daemon.shutdown(streamer)
        pool.closeall()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger.info("Iniciando escucha PEI con streaming...")
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
        bot.notificar_shutdown()
        app_state.streaming_active = False
        pei_daemon.shutdown(streamer)
        pool.closeall()
        sys.exit(0)


if __name__ == "__main__":
    main()
