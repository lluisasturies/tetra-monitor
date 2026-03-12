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
from integrations.email_notifier import EmailNotifier  # noqa: E402
from db.pool import DBPool  # noqa: E402
from db.llamadas import LlamadasDB  # noqa: E402
from db.grupos import GruposDB  # noqa: E402
from db.usuarios import UsuariosDB  # noqa: E402
from pei.hardware.pei_motorola import MotorolaPEI  # noqa: E402
from pei.daemon.pei_daemon import PEIDaemon  # noqa: E402
from streaming import create_streamer  # noqa: E402
from app_state import app_state  # noqa: E402

print()
print("\u2591\u25c0\u2588\u2588\u2588\u2591\u2588\u2588\u2588\u2591\u25c0\u2588\u2588\u2588\u2591\u2588\u2588\u2584\u2591\u2588\u2588\u2588\u2591\u2591\u2591\u2591\u2591\u2588\u2584\u2588\u2591\u2588\u2588\u2588\u2591\u2588\u2588\u2588\u2591\u25c0\u2588\u2588\u2588\u2591\u25c0\u2588\u2588\u2588\u2591\u2588\u2588\u2588\u2591\u2588\u2588\u2584")
print("\u2591\u2591\u2588\u2591\u2591\u2588\u2588\u2588\u2591\u2591\u2588\u2591\u2591\u2588\u2584\u2588\u2591\u2591\u2588\u2588\u2588\u2591\u25c4\u25c4\u25c4\u2591\u2588\u2591\u2588\u2591\u2588\u2591\u2591\u2591\u2591\u2588\u2591\u2588\u2591\u2591\u2588\u2591\u2591\u2591\u2588\u2591\u2591\u2591\u2588\u2591\u2588\u2591\u2588\u2591\u2588\u2584\u2588")
print("\u2591\u2591\u25c0\u2591\u2591\u25c0\u25c0\u25c0\u2591\u2591\u25c0\u2591\u2591\u25c0\u2591\u25c0\u2591\u25c0\u2591\u25c0\u2591\u2591\u2591\u2591\u2591\u25c0\u2591\u25c0\u2591\u25c0\u25c0\u25c0\u2591\u25c0\u25c0\u25c0\u2591\u25c0\u25c0\u25c0\u2591\u2591\u25c0\u2591\u2591\u25c0\u25c0\u25c0\u2591\u25c0\u2591\u25c0")
print("2026 (c) Lluis de la Rubia / LluisAsturies")
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
        logger.info("Configuracion cargada correctamente")
    except FileNotFoundError:
        logger.critical(f"No se encontro config.yaml en {CONFIG_PATH}")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.critical(f"Error parseando config.yaml: {e}")
        sys.exit(1)
    set_level(cfg.get("logging", {}).get("level", "INFO"))
    return cfg


def _validate_env(cfg: dict) -> dict:
    features         = cfg.get("features", {})
    telegram_enabled = features.get("telegram_enabled", True)
    email_enabled    = features.get("email_enabled", False)
    errors = []

    if not os.getenv("DB_USER"):
        errors.append("DB_USER")
    if not os.getenv("DB_PASSWORD"):
        errors.append("DB_PASSWORD")
    if not os.getenv("JWT_SECRET"):
        errors.append("JWT_SECRET")
    if telegram_enabled:
        if not os.getenv("TELEGRAM_TOKEN"):
            errors.append("TELEGRAM_TOKEN")
        if not os.getenv("TELEGRAM_CHAT_ID"):
            errors.append("TELEGRAM_CHAT_ID")
    if email_enabled:
        if not os.getenv("EMAIL_USER"):
            errors.append("EMAIL_USER")
        if not os.getenv("EMAIL_PASSWORD"):
            errors.append("EMAIL_PASSWORD")

    if errors:
        for var in errors:
            logger.critical(f"Variable de entorno obligatoria no definida: {var}")
        sys.exit(1)

    return {
        "db_user":          os.getenv("DB_USER", ""),
        "db_password":      os.getenv("DB_PASSWORD", ""),
        "telegram_token":   os.getenv("TELEGRAM_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "email_user":       os.getenv("EMAIL_USER", ""),
        "email_password":   os.getenv("EMAIL_PASSWORD", ""),
    }


def _init_db(cfg: dict, env: dict) -> tuple[DBPool, LlamadasDB, GruposDB, UsuariosDB]:
    pool = DBPool(
        host=cfg["database"]["host"],
        port=cfg["database"]["port"],
        dbname=cfg["database"]["dbname"],
        user=env["db_user"],
        password=env["db_password"],
    )
    llamadas_db = LlamadasDB(pool)
    grupos_db   = GruposDB(pool)
    usuarios_db = UsuariosDB(pool)

    app_state.pool     = pool
    app_state.llamadas = llamadas_db
    app_state.grupos   = grupos_db
    app_state.usuarios = usuarios_db

    grupos_db.seed_from_yaml(GRUPOS_PATH)

    # Crear usuario admin inicial desde .env si la tabla esta vacia
    api_user = os.getenv("API_USER", "")
    api_hash = os.getenv("API_PASSWORD_HASH", "")
    if api_user and api_hash:
        usuarios_db.seed_admin_desde_env(api_user, api_hash)
    else:
        logger.warning(
            "[main] API_USER / API_PASSWORD_HASH no definidos en .env. "
            "El primer usuario admin debe crearse manualmente via POST /users."
        )

    return pool, llamadas_db, grupos_db, usuarios_db


def _init_bot(cfg: dict, env: dict) -> TelegramBot:
    features = cfg.get("features", {})
    bot = TelegramBot(
        token=env["telegram_token"],
        chat_id=env["telegram_chat_id"],
        enabled=features.get("telegram_enabled", True),
        alerts=cfg.get("telegram", {}).get("alerts", {}),
    )
    app_state.bot = bot
    return bot


def _init_email(cfg: dict, env: dict) -> EmailNotifier:
    features  = cfg.get("features", {})
    email_cfg = cfg.get("email", {})
    to_raw    = email_cfg.get("to", "")
    to        = [t.strip() for t in to_raw.split(",") if t.strip()] if isinstance(to_raw, str) else to_raw
    notifier = EmailNotifier(
        smtp_host=email_cfg.get("smtp_host", "smtp.gmail.com"),
        smtp_port=email_cfg.get("smtp_port", 587),
        user=env["email_user"],
        password=env["email_password"],
        to=to,
        use_tls=email_cfg.get("use_tls", True),
        enabled=features.get("email_enabled", False),
        alerts=email_cfg.get("alerts", {}),
    )
    app_state.email = notifier
    return notifier


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
    email: EmailNotifier, grupos_db: GruposDB, audio_output_dir: str,
) -> PEIDaemon:
    features = cfg.get("features", {})
    return PEIDaemon(
        motorola_pei_cls=MotorolaPEI,
        audio_buffer=audio_buffer,
        stt_processor=stt,
        keyword_filter=kf,
        llamadas_db=llamadas_db,
        afiliacion=afiliacion,
        bot=bot,
        email=email,
        grupos_db=grupos_db,
        port=cfg["pei"].get("port", ""),
        baudrate=cfg["pei"]["baudrate"],
        audio_output_dir=audio_output_dir,
        retention_days=cfg["audio"].get("retention_days", 7),
        recording_enabled=features.get("recording_enabled", True),
        processing_enabled=features.get("processing_enabled", True),
        save_all_calls=features.get("save_all_calls", False),
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
    features   = cfg.get("features", {})
    stream_cfg = cfg.get("streaming", {})

    if not features.get("streaming_enabled", False):
        app_state.streaming_active = False
        return None

    stream_cfg["samplerate"] = cfg["audio"]["sample_rate"]
    stream_cfg["channels"]   = cfg["audio"]["channels"]
    streamer = create_streamer(stream_cfg)

    if streamer is None:
        logger.warning(
            "[Streaming] streaming_enabled=true pero no hay ningun streamer activo. "
            "Define zello_url, rtmp_url o icecast_url en la seccion 'streaming' del config.yaml."
        )
        app_state.streaming_active = False
        return None

    app_state.streaming_active = streamer.running
    return streamer


def main():
    cfg      = _load_config()
    env      = _validate_env(cfg)
    features = cfg.get("features", {})

    audio_output_dir = os.path.join(PROJECT_ROOT, cfg["audio"].get("output_dir", "data/audio"))

    afiliacion = AfiliacionConfig(AFILIACION_PATH)
    app_state.afiliacion = afiliacion

    pool, llamadas_db, grupos_db, usuarios_db = _init_db(cfg, env)
    bot                                        = _init_bot(cfg, env)
    email                                      = _init_email(cfg, env)
    afiliacion.set_bot(bot)
    audio_buffer, stt, kf = _init_audio(cfg, audio_output_dir)
    pei_daemon            = _init_pei(
        cfg, audio_buffer, stt, kf, llamadas_db, afiliacion, bot, email,
        grupos_db, audio_output_dir
    )

    streaming_enabled  = features.get("streaming_enabled", False)
    recording_enabled  = features.get("recording_enabled", True)
    processing_enabled = features.get("processing_enabled", True)
    telegram_enabled   = features.get("telegram_enabled", True)
    email_enabled      = features.get("email_enabled", False)
    save_all_calls     = features.get("save_all_calls", False)
    watchdog_timeout   = cfg["pei"].get("watchdog_timeout", 60)
    max_rec_seconds    = cfg["audio"].get("max_recording_seconds", 120)

    logger.info(f"Grabacion de audio       : {'ACTIVADA'  if recording_enabled  else 'DESACTIVADA'}")
    logger.info(f"Procesado PEI            : {'ACTIVADO'  if processing_enabled else 'DESACTIVADO'}")
    logger.info(f"Telegram                 : {'ACTIVADO'  if telegram_enabled   else 'DESACTIVADO'}")
    logger.info(f"Email                    : {'ACTIVADO'  if email_enabled      else 'DESACTIVADO'}")
    logger.info(f"Streaming                : {'ACTIVADO'  if streaming_enabled  else 'DESACTIVADO'}")
    logger.info(f"Guardado en BD           : {'TODAS las llamadas' if save_all_calls else 'Solo con keyword'}")
    logger.info(f"Watchdog PEI             : {watchdog_timeout}s (0=desactivado)")
    logger.info(f"Limite grabacion         : {max_rec_seconds}s (0=desactivado)")

    _init_api(cfg)
    streamer = _init_streaming(cfg)
    email.notificar_startup()

    def _signal_handler(sig, frame):
        logger.info("Senal de interrupcion recibida, cerrando aplicacion...")
        email.notificar_shutdown()
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
        logger.info("Interrupcion por teclado recibida")
        email.notificar_shutdown()
        app_state.streaming_active = False
        pei_daemon.shutdown(streamer)
        pool.closeall()
        sys.exit(0)


if __name__ == "__main__":
    main()
