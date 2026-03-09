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
* 📲 **Notificaciones** por Telegram Bot API
* 🗄️ **PostgreSQL** para almacenamiento
* 🎧 **Streaming de audio** via Icecast o RTMP
* 🔗 **API REST** con autenticación JWT

---

## Estructura del proyecto
```
tetra-monitor/
├── config/
│   ├── config.yaml          # Configuración principal
│   ├── keywords.yaml        # Palabras clave para filtrado (recarga en caliente)
│   └── scan.yaml            # GSSI y scan list (modificable via API)
├── data/
│   ├── audio/               # Grabaciones .flac
│   └── db/
│       └── schema.sql       # DDL de PostgreSQL
├── logs/                    # Logs de la aplicación
├── scripts/
│   ├── setup.sh                          # Instalación completa
│   ├── start.sh                          # Arranque del daemon
│   └── tetra-monitor.service.template    # Plantilla del unit file systemd
├── Makefile                 # Atajos para operaciones comunes
└── src/
    ├── main.py              # Punto de entrada (daemon + API en un solo proceso)
    ├── app_state.py         # Contenedor de dependencias compartidas
    ├── api/
    │   └── api.py           # API REST (FastAPI + JWT)
    ├── audio/
    │   ├── audio_buffer.py  # Captura y grabación de audio
    │   └── audio_cleanup.py # Limpieza automática de ficheros FLAC
    ├── core/
    │   ├── logger.py        # Logger centralizado
    │   ├── scan_config.py   # Config de scan dinámica (mtime IPC)
    │   └── stt_processor.py # Transcripción con Whisper
    ├── db/
    │   ├── pool.py          # ThreadedConnectionPool compartido
    │   └── llamadas.py      # Queries sobre la tabla llamadas
    ├── filters/
    │   └── keyword_filter.py # Filtrado por palabras clave (recarga en caliente)
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

TELEGRAM_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Genera un secreto seguro con: openssl rand -hex 32
JWT_SECRET=genera_un_secreto_largo_y_aleatorio
API_USER=admin
API_PASSWORD=genera_una_contraseña_segura
```

> `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` solo son obligatorias si `telegram.enabled: true` en `config.yaml`.

### 3. Ejecutar el setup
El script instala automáticamente Python, PostgreSQL, ffmpeg, las dependencias Python, pre-descarga el modelo Whisper y aplica el schema de base de datos:
```bash
make setup
# o directamente: sudo bash scripts/setup.sh
```

---

## Arranque
```bash
make start
# o directamente: bash scripts/start.sh
```

El daemon PEI y la API REST arrancan juntos en el mismo proceso. La API queda disponible en `http://raspberrypi:8000`.

---

## Makefile
```bash
make setup              # Instala dependencias y prepara el entorno
make start              # Arranca el monitor en primer plano
make stop               # Detiene el servicio systemd
make restart            # Reinicia el servicio systemd
make status             # Muestra el estado del servicio systemd
make logs               # Muestra los logs en tiempo real (journalctl)
make logs-file          # Muestra los logs en tiempo real (fichero local)
make install-service    # Instala tetra-monitor como servicio systemd
make uninstall-service  # Elimina el servicio systemd
make update             # git pull + reinicia el servicio
```

---

## Systemd (producción)
Para que el daemon arranque automáticamente con la RPi y se reinicie si falla:
```bash
make install-service
sudo systemctl start tetra-monitor
```

`make install-service` genera el unit file automáticamente con el usuario actual y la ruta del proyecto — no hace falta editar nada a mano.

```bash
make logs       # logs en tiempo real (journalctl)
make logs-file  # logs en tiempo real (fichero local)
make status     # estado del servicio
make restart    # reiniciar
make stop       # parar
```

---

## Flags de activación
Los siguientes componentes pueden activarse y desactivarse desde `config/config.yaml` sin tocar el código:

| Flag | Sección | Efecto si `false` |
|---|---|---|
| `recording_enabled` | `audio` | No graba ficheros de audio en disco |
| `processing_enabled` | `pei` | Ignora todos los eventos PEI |
| `enabled` | `telegram` | No envía alertas por Telegram |
| `enabled` | `streaming` | No inicia el streaming de audio |

---

## API REST
Todos los endpoints (excepto `/health`) requieren autenticación JWT.

### Obtener token
```bash
curl -X POST http://raspberrypi:8000/auth/token \
  -d "username=admin&password=tu_password"
```
Respuesta:
```json
{"access_token": "eyJ...", "token_type": "bearer"}
```

### Endpoints

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/health` | Healthcheck público |
| `POST` | `/auth/token` | Obtener token JWT |
| `GET` | `/calls` | Listar llamadas (param: `limit`) |
| `GET` | `/calls/{id}` | Detalle de una llamada |
| `GET` | `/scan-config` | Ver GSSI y scan list activos |
| `POST` | `/update-gssi` | Cambiar GSSI activo |
| `POST` | `/update-scanlist` | Cambiar scan list |

### Ejemplos
```bash
TOKEN=$(curl -s -X POST http://raspberrypi:8000/auth/token \
  -d "username=admin&password=tu_password" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -H "Authorization: Bearer $TOKEN" http://raspberrypi:8000/calls?limit=10

curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gssi": "1234567"}' \
  http://raspberrypi:8000/update-gssi
```

---

## Arquitectura
El sistema corre en **un único proceso** con dos componentes concurrentes:

- **Daemon PEI** — escucha la radio por puerto serie, graba audio, transcribe y alerta
- **API REST** — corre en un hilo separado, expone endpoints para consultar llamadas y modificar la configuración

La comunicación entre ambos se hace a través de `config/scan.yaml`. Cuando la API actualiza el GSSI o la scan list, escribe en el fichero. El daemon comprueba el `mtime` cada 5 segundos y aplica los cambios a la radio si detecta modificaciones. Lo mismo aplica a `config/keywords.yaml`, que también se recarga en caliente.

Solo las llamadas que contienen alguna palabra clave se guardan en base de datos y generan alerta por Telegram. El audio de llamadas sin keyword se elimina automáticamente.

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
