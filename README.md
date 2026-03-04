# TETRA Monitor - Raspberry Pi 5

Proyecto para monitorización selectiva de red TETRA experimental usando:

- Motorola MTM5400
- Raspberry Pi 5
- PostgreSQL para almacenamiento
- Whisper/Vosk para Speech-to-Text
- Notificaciones por Telegram
- API REST para consultar eventos

## Estructura del proyecto

- `src/` → Código Python modular
- `config/` → Configuraciones y palabras clave
- `scripts/` → Instalación y arranque
- `data/` → Audio grabado y base de datos
- `logs/` → Logs de ejecución

## Instalación

```bash
cd scripts
chmod +x setup_env.sh
./setup_env.sh