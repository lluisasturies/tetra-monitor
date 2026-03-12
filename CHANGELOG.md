# Changelog

## [Unreleased]

### Added
- **Sistema de usuarios en BD** (`db/usuarios.py`, migración `db/migrations/003_usuarios.sql`):
  - Tabla `usuarios` con roles `admin`, `operator` y `viewer`
  - Tabla `refresh_tokens` persistente en BD (los tokens sobreviven reinicios del proceso y se pueden revocar individualmente)
  - `seed_admin_desde_env()`: migración sin rotura desde el sistema anterior basado en `API_USER`/`API_PASSWORD_HASH`
  - Rotación de tokens: cada refresh token se invalida al ser consumido y se emite uno nuevo
  - `limpiar_tokens_expirados()` para mantenimiento periódico
- **Endpoints de usuarios** (solo `admin`):
  - `GET /users` — listar usuarios
  - `POST /users` — crear usuario
  - `GET /users/{id}` — detalle de usuario
  - `PUT /users/{id}` — modificar usuario (email, rol, activo, contraseña)
  - `DELETE /users/{id}` — desactivar usuario (soft-delete + revocación de tokens)
  - `GET /users/me` — perfil del usuario autenticado (cualquier rol)
- **Autorización por rol en la API**:
  - `viewer` — lectura: `/calls`, `/keywords`, `/afiliacion`, `/groups`, `/folders`, `/scan-lists`
  - `operator` — escritura: keywords, afiliacion, grupos, carpetas
  - `admin` — gestión de usuarios + todo lo anterior
- **Nuevos endpoints de auth**:
  - `POST /auth/logout` — revoca todos los tokens del usuario autenticado
- `app_state.usuarios` — nueva referencia a `UsuariosDB` en el estado global
- Tests unitarios completos para `UsuariosDB` (`tests/test_usuarios_db.py`): creación, validación de roles, hash de contraseña, seed, refresh tokens (válido, revocado, expirado, usuario inactivo)

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
- `main._validate_env()`: `API_USER` y `API_PASSWORD_HASH` ya no son obligatorios al arranque — solo se usan como semilla del primer admin si la tabla `usuarios` está vacía

### Notes
- **Migración**: ejecutar `db/migrations/003_usuarios.sql` antes de arrancar esta versión
- Los usuarios existentes que usaban `API_USER`/`API_PASSWORD_HASH` se migran automáticamente en el primer arranque si la tabla `usuarios` está vacía

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
