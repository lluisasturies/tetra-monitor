# TETRA Monitor
```
░▀█▀░█▀▀░▀█▀░█▀▄░█▀▀░░░░░█▄█░█▀▀░█▀▀░▀█▀░▀█▀░█▀▀░█▀▄
░░█░░█▀▀░░█░░█▀▄░█▀▀░▄▄▄░█░█░█░░░█░█░░█░░░█░░█░█░█▀▄
░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░░░░░▀░▀░▀▀▀░▀▀▀░▀▀▀░░▀░░▀▀▀░▀░▀
```

Sistema de monitorización de redes TETRA sobre Raspberry Pi. Escucha eventos PTT, transcribe el audio con Whisper, filtra por palabras clave y envía alertas por Telegram.

---

## Instalación rápida

```bash
git clone https://github.com/lluisasturies/tetra-monitor.git
cd tetra-monitor
make init      # copia todos los .example a su versión local
# edita config/config.yaml y .env con tus valores
make setup     # instala Python, PostgreSQL, ffmpeg, Whisper y aplica el schema
make set-password
make start
```

Para instalar como servicio systemd (arranque automático con la RPi):
```bash
make install-service
```

---

## Configuración

Todos los ficheros de configuración se generan con `make init` a partir de sus plantillas `.example`. Ninguno se versiona.

**`.env`** — variables sensibles:
```env
DB_USER=tetra
DB_PASSWORD=changeme
JWT_SECRET=        # openssl rand -hex 32
API_USER=admin
API_PASSWORD_HASH= # make set-password
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=
# Solo si streaming.zello_url está definido:
ZELLO_USERNAME=
ZELLO_PASSWORD=
ZELLO_TOKEN=
```

**`config/config.yaml`** — el resto de parámetros: hardware PEI, audio, STT, BD, API, streaming y notificaciones. Ver `config/config.yaml.example` como referencia completa.

---

## Streaming

Solo puede estar activo un backend a la vez (`zello_url` > `rtmp_url` > `icecast_url`):

```yaml
streaming:
  zello_url: "mi-canal"           # PTT-aware — abre/cierra con cada transmisión
  # rtmp_url: "rtmp://..."        # stream continuo
  # icecast_url: "icecast://..."  # stream continuo
```

Zello requiere credenciales de desarrollador en `.env` y `pip install websockets opuslib`.

---

## Comandos útiles

```bash
make start / stop / restart / status
make logs / logs-file
make update           # git pull + reinicia el servicio
make backup-db        # volcado de la BD en data/backups/
make setup-https      # nginx con TLS (certificado autofirmado)
```

---

## API REST

Todos los endpoints (excepto `/health` y `/auth/*`) requieren JWT.

```bash
curl -X POST http://raspberrypi:8000/auth/token \
  -d "username=admin&password=tu_password"
```

Endpoints principales: `/calls`, `/keywords`, `/afiliacion`, `/groups`, `/folders`, `/scan-lists`. Ver documentación interactiva en `http://raspberrypi:8000/docs`.

---

## Licencia
Apache 2.0 — 2026 Lluis de la Rubia / LluisAsturies
