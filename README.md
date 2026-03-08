# 📡 TETRA Monitor
```
░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░░░░░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄
░░█░░█▀▀░░█░░█▀▄░█▀█░▄▄▄░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄
░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░░░░░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀
```
Sistema de monitorización de redes **TETRA** en tiempo real sobre **Raspberry Pi 5**, con transcripción de voz, filtrado por palabras clave, alertas por Telegram y streaming de audio.

---

## ✨ Características
- 📻 **Lectura de radio TETRA** vía interfaz PEI Motorola MTM5400 (comandos AT por serie)
- 🎙️ **Grabación de audio** con pre-buffer configurable para no perder el inicio de la llamada
- 🗣️ **Speech-to-Text** con [Whisper](https://github.com/openai/whisper)
- 🔍 **Filtrado por palabras clave** sobre las transcripciones
- 🗄️ **Almacenamiento en PostgreSQL** de llamadas filtradas con su transcripción y ruta de audio
- 📲 **Alertas automáticas por Telegram** cuando se detecta una palabra clave en la llamada
- 🎧 **Streaming de audio** en tiempo real vía RTMP o Icecast/MP3
- 🔗 **API REST** (FastAPI) para consultar eventos y gestionar la configuración

---

## 🗂️ Estructura del proyecto
```
tetra-monitor/
├── src/
│   ├── main.py                  # Punto de entrada principal
│   ├── core/
│   │   ├── database.py          # Conexión y operaciones PostgreSQL
│   │   ├── logger.py            # Sistema de logging con rotación
│   │   ├── scan_config.py       # Configuración de GSSI y scan list
│   │   └── stt_processor.py     # Transcripción Speech-to-Text (Whisper)
│   ├── audio/
│   │   └── audio_buffer.py      # Captura de audio con pre-buffer
│   ├── api/
│   │   └── api.py               # API REST (FastAPI)
│   ├── filters/
│   │   └── keyword_filter.py    # Filtro de palabras clave
│   ├── integrations/
│   │   └── telegram_bot.py      # Notificaciones Telegram
│   ├── pei/
│   │   ├── pei_motorola.py      # Comunicación serie con Motorola MTM5400
│   │   └── pei_daemon.py        # Bucle principal de escucha del PEI
│   └── streaming/
│       ├── __init__.py          # Factory de streamers
│       ├── base_streamer.py     # Clase base (ffmpeg)
│       ├── icecast_streamer.py  # Streaming Icecast/MP3
│       └── rtmp_streamer.py     # Streaming RTMP/AAC
├── config/
│   ├── config.yaml              # Configuración general
│   ├── keywords.yaml            # Palabras clave a detectar
│   └── scan.yaml                # GSSI y scan list activos
├── data/
│   ├── audio/                   # Grabaciones de llamadas (.flac)
│   └── db/
│       └── schema.sql           # Esquema de la base de datos
├── logs/                        # Logs rotativos (generado automáticamente)
├── scripts/
│   ├── setup.sh                 # Instalación de dependencias
│   └── start.sh                 # Arranque del servicio
├── .env.example                 # Plantilla de variables de entorno
└── .gitignore
```

---

## 🛠️ Requisitos
### Hardware
- Raspberry Pi 5 (recomendado 4 GB RAM o más)
- Motorola MTM5400 con cable PEI (RS-232 o USB-serie)
- Micrófono USB o tarjeta de sonido compatible

### Software
- Python 3.11+
- PostgreSQL 14+
- ffmpeg (para streaming)

---

## ⚙️ Instalación
### 1. Clonar el repositorio
```bash
git clone https://github.com/lluisasturies/tetra-monitor.git
cd tetra-monitor
```

### 2. Instalar dependencias del sistema
```bash
chmod +x scripts/setup.sh
scripts/setup.sh
```

### 3. Configurar variables de entorno
```bash
cp .env.example .env
nano .env
```

Rellena los valores reales en `.env`:

### 4. Ajustar la configuración
Edita `config/config.yaml` según tu entorno:

```yaml
pei:
  port: "/dev/ttyUSB0"   # Puerto serie del Motorola
  baudrate: 9600

audio:
  device_index: 1         # Índice del micrófono (ver sección "Micrófono")
  sample_rate: 16000
  prebuffer_seconds: 5

stt:
  model: "base"           # tiny/base en RPi, small/medium si hay más RAM
  language: "es"

streaming:
  enabled: true
  rtmp_url: rtmp://localhost/live/tetra
```

Edita `config/keywords.yaml` con las palabras clave a detectar:

```yaml
keywords:
  - "intento de intrusión"
  - "falla cámara"
  - "emergencia"
```

---

## ▶️ Arrancar TETRA Monitor
```bash
chmod +x scripts/start.sh
scripts/start.sh
```

### API REST
```bash
cd src
uvicorn api:app --host 0.0.0.0 --port 8000
```

Documentación interactiva disponible en `http://localhost:8000/docs`.

### Ejecutar como servicio systemd (recomendado para producción)
```bash
sudo nano /etc/systemd/system/tetra-monitor.service
```

```ini
[Unit]
Description=TETRA Monitor
After=network.target postgresql.service

[Service]
User=pi
WorkingDirectory=/home/pi/tetra-monitor/src
EnvironmentFile=/home/pi/tetra-monitor/.env
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable tetra-monitor
sudo systemctl start tetra-monitor
```

---

## 🔗 API REST
Todos los endpoints (excepto `/health`) requieren la cabecera `x-api-key`.

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/health` | Healthcheck público |
| `GET` | `/events?limit=50` | Lista los últimos eventos |
| `GET` | `/events/{id}` | Detalle de un evento por ID |
| `GET` | `/scan-config` | Obtiene GSSI y scan list actuales |
| `POST` | `/update-gssi` | Actualiza el GSSI activo |
| `POST` | `/update-scanlist` | Actualiza la scan list activa |

Ejemplo:

```bash
curl -H "x-api-key: tu_api_key" http://localhost:8000/events?limit=10
```

---

## 🎤 Identificar el micrófono
Si no sabes el `device_index` de tu micrófono:

```python
import sounddevice as sd
print(sd.query_devices())
```

Busca tu dispositivo en la lista y usa su índice en `config.yaml`.

---

## 📋 Logs
Los logs se guardan en `logs/` con rotación automática (10 MB por fichero, 10 copias):

| Fichero | Contenido |
|---|---|
| `logs/tetra_monitor.log` | Log general de la aplicación |
| `logs/calls.log` | Registro de llamadas |

El nivel de log se configura en `config.yaml`:

```yaml
logging:
  level: INFO   # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

---

## 🔒 Seguridad
- Las credenciales se gestionan exclusivamente mediante variables de entorno (`.env`)
- La API REST requiere `x-api-key` en todas las peticiones (excepto `/health`)
- Para streaming remoto, usa siempre **RTMPS** o **HTTPS/WSS** para Icecast

---

## 📄 Licencia
Apache 2.0 — © 2026 Lluis de la Rubia / LluisAsturies
