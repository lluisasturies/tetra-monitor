# Changelog

## [Unreleased]

### Fixed
- `AudioBuffer.start_recording()`: race condition al copiar el pre-buffer desde el callback de sounddevice — añadido `threading.Lock` para proteger el acceso a `_record_buffer.queue`
- `ZelloStreamer.send_audio()`: import de `numpy` movido al nivel de módulo junto al resto de dependencias opcionales (era un import dentro del hot path de audio)
- `pei_motorola.set_scan_list()`: comando AT corregido de `AT+CGSSI` (consulta de GSSI) a `AT+CTSL` (cambio de scan list según ETSI EN 300 392-5)
- `TelegramBot._send_with_retry()`: los envíos ya no bloquean el hilo del daemon PEI — se procesan en un hilo dedicado via `queue.Queue`
- `main._init_streaming()`: advertencia explícita si `streaming_enabled=true` pero no hay ninguna URL configurada
- `app_state.refresh_tokens`: movido de atributo de clase a atributo de instancia para evitar estado compartido entre instancias

### Refactored
- `TelegramBot`: envíos Telegram desacoplados del hilo principal mediante cola FIFO + hilo daemon `telegram-sender`
- `LlamadasDB`: métricas de salud (`calls_today`, `last_call_at`) movidas a `get_health_metrics()` — antes se hacían queries directas desde `api.py` rompiendo la separación de capas
- `api.py`: cuatro helpers `_require_*()` unificados en `_require(attr, detail)` genérico
- `streaming/__init__.py`: activación de Zello unificada con RTMP/Icecast — se usa `zello_url` en lugar de `zello.enabled + channel`; credenciales Zello en `.env`

### Added
- Tests de integración: ciclo completo `CALL_START → PTT_START → PTT_END` con Zello, RTMP y sin streamer (`test_pei_daemon.py`)
- Tests de `TelegramBot` incluyendo verificación del flujo end-to-end via cola async (`test_telegram_bot.py`)

---

## [0.1.0] — 2026-01-xx — Primera versión funcional

### Added
- Captura de eventos TETRA via Motorola PEI (AT commands sobre puerto serie)
- Grabación de audio con pre-buffer configurable (`sounddevice` + `soundfile` FLAC)
- Speech-to-Text con OpenAI Whisper (hilo dedicado, no bloquea el daemon)
- Filtro de palabras clave con recarga en caliente desde `keywords.yaml`
- Notificaciones Telegram y Email (SMTP) con flags de activación por tipo de evento
- Almacenamiento de llamadas en PostgreSQL con pool de conexiones (`psycopg2`)
- API REST con FastAPI: JWT auth, rate limiting, CORS, modo standalone
- Endpoints: `/calls`, `/keywords`, `/afiliacion`, `/groups`, `/folders`, `/scan-lists`
- Streaming de audio: Zello (PTT-aware), RTMP y Icecast (continuos)
- Watchdog de reconexión automática del puerto serie
- Timeout máximo de grabación configurable
- Limpieza periódica de ficheros FLAC según `retention_days`
- Semilla inicial de grupos, carpetas y scan lists desde `grupos.yaml`
- Servicio systemd con `make install-service`
- HTTPS opcional con nginx como proxy inverso (certificado autofirmado RSA 4096)
- `make init/setup/start/stop/restart/logs/backup-db/update/reload-grupos`
