```
░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄
░░█░░█▀▀░░█░░█▀▄░█▀█░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄
░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀
```
Proyecto para monitorización de una red TETRA usando:

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
- `data/` → Grabaciones de audio
- `logs/` → Logs de ejecución

## Instalación
```bash
chmod +x scripts/setup.sh
scripts/setup.sh
```

## Iniciar
```bash
chmod +x scripts/start.sh
scripts/start.sh
```