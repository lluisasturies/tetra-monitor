# Changelog

Todos los cambios notables de este proyecto se documentan aquí.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.0.0/).
Versionado según [Semantic Versioning](https://semver.org/lang/es/).

---

## [Unreleased]

---

## [1.1.0] - 2026-03-10

### Added
- Tests unitarios para `KeywordFilter`, parser PEI (`MotorolaPEI`) y `AfiliacionConfig` (37 tests, 0 fallos)
- GitHub Actions CI: lint con `ruff` + `pytest` en cada push/PR a `develop` y `master`
- Rama `develop` como rama de trabajo; `master` queda protegida como rama de producción
- `make reload-grupos`: recarga el catálogo de grupos, carpetas y scan lists desde `config/grupos.yaml` sin reiniciar el servicio
- Script `scripts/reload_grupos.py` con soporte `--dry-run` y `--yes`

### Changed
- `src/main.py` refactorizado: código plano extraído en funciones de inicialización (`_load_config`, `_validate_env`, `_init_db`, `_init_bot`, `_init_audio`, `_init_pei`, `_init_api`, `_init_streaming`)

### Fixed
- Errores de lint `ruff`: E402 en imports post-`load_dotenv`, E701 en ifs en una línea, F401 en imports sin usar

---

## [1.0.0] - 2026-03-04

### Added
- Captura de eventos TETRA vía PEI Motorola (comandos AT sobre puerto serie)
- Grabación de audio con `sounddevice` + `soundfile` y prebuffer configurable
- Transcripción Speech-to-Text con OpenAI Whisper
- Filtro de palabras clave con recarga en caliente desde `config/keywords.yaml`
- Notificaciones por Telegram Bot API
- Almacenamiento de llamadas en PostgreSQL con pool de conexiones
- Catálogo de grupos, carpetas y scan lists en BD con semilla desde YAML
- API REST con FastAPI: autenticación JWT + refresh tokens, rate limiting, CORS
- Endpoints: `/health`, `/auth/*`, `/calls`, `/afiliacion`, `/groups`, `/folders`, `/scan-lists`
- Streaming de audio vía Icecast o RTMP
- Proxy inverso nginx con TLS (certificado autofirmado, opcional)
- Servicio systemd con `make install-service`
- Makefile con targets: `setup`, `start`, `stop`, `restart`, `logs`, `update`, `set-password`, `setup-https`
- Configuración por flags en `config/config.yaml`: grabación, procesado PEI, Telegram, streaming
- Validación regex de comandos AT antes de enviarlos a la radio
