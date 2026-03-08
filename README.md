# TETRA Monitor
```
░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░░░░░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄
░░█░░█▀▀░░█░░█▀▄░█▀█░▄▄▄░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄
░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░░░░░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀
```

Sistema de monitorización de redes TETRA sobre Raspberry Pi. Escucha eventos PTT en tiempo real, transcribe el audio con Whisper, filtra por palabras clave y envía alertas por Telegram.

* 📡 **Captura de eventos TETRA** Motorola PEI (AT commands sobre serie)
* 🖥️ **Grabación de audio** `sounddevice` + `soundfile`
* 🗣️ **Speech-to-Text** con OpenAI Whisper
* 📲 **Notificaciones** por Telegram Boot API
* 🗄️ **PostgreSQL** para almacenamiento
* 🎧 **Streaming de audio** via Icecast o RTMP
* 🔗 **API REST** para consultar eventos

---

## Estructura del proyecto
```
tetra-monitor/
├── config/
│   ├── config.yaml          # Configuración principal
│   ├── keywords.yaml        # Palabras clave para filtrado
│   └── scan.yaml            # GSSI y scan list (modificable via API)
├── data/
│   ├── audio/               # Grabaciones .flac
│   └── db/
│       └── schema.sql       # DDL de PostgreSQL
├── logs/                    # Logs de la aplicación
├── scripts/
│   ├── setup.sh             # Instalación completa
│   └── start.sh             # Arranque del daemon
└── src/
    ├── main.py              # Punto de entrada
    ├── api/
    │   └── api.py           # API REST (FastAPI)
    ├── audio/
    │   └── audio_buffer.py  # Captura y grabación de audio
    ├── core/
    │   ├── database.py      # Conexión y queries PostgreSQL
    │   ├── logger.py        # Logger centralizado
    │   ├── scan_config.py   # Config de scan dinámica (mtime IPC)
    │   ├── scan_config.py   # Config de scan dinámica
    │   └── stt_processor.py # Transcripción con Whisper
    ├── filters/
    │   └── keyword_filter.py # Filtrado por palabras clave
    ├── integrations/
    │   └── telegram_bot.py  # Notificaciones Telegram
    ├── pei/
    │   ├── daemon/
    │   │   └── pei_daemon.py    # Bucle principal de eventos
    │   ├── hardware/
    │   │   └── pei_motorola.py  # Comunicación serie con la radio
    │   └── models/
    │       └── pei_event.py     # Dataclass PEIEvent
    └── streaming/
        ├── base_streamer.py     # Clase base ffmpeg
        ├── icecast_streamer.py  # Streaming a Icecast
        └── rtmp_streamer.py     # Streaming RTMP
```

---

## Instalación
### 1. Clonar el repositorio
```bash
git clone https://github.com/lluisasturies/tetra-monitor.git
cd tetra-monitor
```

### 2. Crear el fichero de configuración
```bash
cp .env.example .env
nano .env
```

Variables necesarias en `.env`:
```env
DB_USER=tetra
DB_PASSWORD=changeme
DB_NAME=tetra
DB_HOST=localhost
DB_PORT=5432

TELEGRAM_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

JWT_SECRET=your_jwt_secret
API_KEY=your_api_key
```

### 3. Ejecutar el setup
El script instala automáticamente Python, PostgreSQL, ffmpeg, las dependencias Python y aplica el schema de base de datos:
```bash
sudo bash scripts/setup.sh
```

---

## Arranque
```bash
bash scripts/start.sh
```

La API REST corre por separado (proceso independiente):
```bash
cd src
uvicorn api.api:app --host 0.0.0.0 --port 8000
```

---

## API REST
Todos los endpoints (excepto `/health`) requieren el header `x-api-key`.

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/health` | Healthcheck público |
| `GET` | `/events` | Listar eventos (param: `limit`) |
| `GET` | `/events/{id}` | Detalle de un evento |
| `GET` | `/scan-config` | Ver GSSI y scan list activos |
| `POST` | `/update-gssi` | Cambiar GSSI activo |
| `POST` | `/update-scanlist` | Cambiar scan list |

### Ejemplo
```bash
curl -H "x-api-key: your_api_key" http://raspberrypi:8000/events?limit=10
```
```bash
curl -X POST \
  -H "x-api-key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"gssi": "1234567"}' \
  http://raspberrypi:8000/update-gssi
```

---

## Arquitectura
El sistema corre en **dos procesos independientes**:

- **Daemon PEI** (`main.py`) — escucha la radio por puerto serie, graba audio, transcribe y alerta
- **API REST** (`uvicorn`) — expone endpoints para consultar eventos y modificar la configuración

La comunicación entre procesos se hace a través de `config/scan.yaml`. Cuando la API actualiza el GSSI o la scan list, escribe en el fichero. El daemon comprueba el `mtime` del fichero cada 5 segundos y aplica los cambios a la radio si detecta modificaciones.

---

## Protocolo PEI (ETSI EN 300 392-5)
Los eventos TETRA se parsean según el estándar ETSI:

| Comando AT | Evento | Acción |
|---|---|---|
| `+CTXG` | Transmission Grant | PTT_START / PTT_END |
| `+CDTXC` | Down Transmission Ceased | PTT_END |
| `+CTICN` | Incoming Call Notification | CALL_START (captura GSSI y SSI) |
| `+CTCC` | Call Connect | CALL_CONNECTED |
| `+CTCR` | Call Release | CALL_END |
| `+CTXD` | Transmit Demand | TX_DEMAND |

> **Nota:** Los índices de parámetros de `+CTICN` dependen del perfil `+CTSDC` configurado en la radio. Verificar con logs reales del puerto serie antes de poner en producción.

---

## Licencia
Apache 2.0 — © 2026 Lluis de la Rubia / LluisAsturies