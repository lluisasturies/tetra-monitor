░▀█▀░█▀▀░▀█▀░█▀▄░█▀█░█▄█░█▀█░█▀█░▀█▀░▀█▀░█▀█░█▀▄
░░█░░█▀▀░░█░░█▀▄░█▀█░█░█░█░█░█░█░░█░░░█░░█░█░█▀▄
░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░▀░▀░▀▀▀░▀░▀░▀▀▀░░▀░░▀▀▀░▀░▀

# 🌐 TETRA Monitor
Proyecto para **monitorización de redes TETRA** usando:

* 📡 **Motorola MTM5400**
* 🖥️ **Raspberry Pi 5**
* 🗄️ **PostgreSQL** para almacenamiento
* 🗣️ **Whisper** para Speech-to-Text
* 📲 **Notificaciones por Telegram**
* 🔗 **API REST** para consultar eventos
* 🎧 **Streaming de audio** via Icecast o RTMP

---

## 🗂️ Estructura del proyecto
```
tetra-monitor/
├── src/
│   ├── api/              # API REST (FastAPI)
│   ├── audio/            # Captura y buffer de audio
│   ├── core/             # Base de datos, logger, STT, configuración
│   ├── filters/          # Filtro de palabras clave
│   ├── integrations/     # Telegram
│   ├── pei/              # Comunicación con la radio (PEI)
│   ├── streaming/        # Streaming Icecast / RTMP
│   └── main.py
├── config/               # config.yaml y keywords
├── data/db/              # Datos persistentes
├── scripts/              # Scripts de instalación y arranque
├── .env                  # Variables de entorno (no subir a git)
└── requirements.txt
```

---

## ⚙️ Instalación
```bash
chmod +x scripts/setup.sh
scripts/setup.sh
```

---

## 🔧 Configuración
Copia `.env.example` a `.env` y rellena los valores:
```bash
cp .env.example .env
```

Variables necesarias:
```env
API_KEY=tu_api_key_aqui
DB_PASSWORD=tu_password_aqui
DB_USER=tetra
TELEGRAM_TOKEN=tu_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id_aqui
```

---

## ▶️ Iniciar TETRA Monitor
```bash
chmod +x scripts/start.sh
scripts/start.sh
```

---

## 🎧 Streaming de audio
El sistema soporta dos modos de streaming:

- **Icecast** — para servidores de streaming de audio (MP3)
- **RTMP** — para plataformas compatibles con FLV/AAC

Configura la URL de destino en `config/config.yaml`.

---

## 📝 Notas importantes
* 📂 Logs y grabaciones se guardan en `logs/` y `data/audio/`
* ⚙️ Personaliza palabras clave y configuraciones en `config/`
* 🔒 Para producción remota: usar HTTPS y autenticación en la API
* 🤖 El modelo Whisper por defecto es `base` — en Raspberry Pi se recomienda no usar modelos más grandes