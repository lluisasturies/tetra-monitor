# TETRA Monitor
```
░▀█▀░█▀▀░▀█▀░█▀▄░█▀▀░░░░░█▄█░█▀▀░█▀▀░▀█▀░▀█▀░█▀▀░█▀▄
░░█░░█▀▀░░█░░█▀▄░█▀▀░▄▄▄░█░█░█░░░█░█░░█░░░█░░█░█░█▀▄
░░▀░░▀▀▀░░▀░░▀░▀░▀░▀░░░░░▀░▀░▀▀▀░▀▀▀░▀▀▀░░▀░░▀▀▀░▀░▀
```

Sistema de monitorización de redes TETRA sobre Raspberry Pi. Escucha eventos PTT en tiempo real, transcribe el audio con Whisper, filtra por palabras clave y envía alertas por Telegram.

* 📡 **Captura de eventos TETRA** — Motorola PEI (AT commands sobre serie)
* 🖥️ **Grabación de audio** — `sounddevice` + `soundfile`
* 🗣️ **Speech-to-Text** — OpenAI Whisper
* 📲 **Notificaciones** — Telegram Bot API
* 🗄️ **PostgreSQL** — almacenamiento de llamadas, catálogo de grupos y scan lists
* 🎧 **Streaming de audio** — Icecast o RTMP
* 🔗 **API REST** — FastAPI con autenticación JWT + rate limiting
* 🔒 **HTTPS opcional** — nginx como proxy inverso con TLS

---

## Estructura del proyecto
```
tetra-monitor/
├── config/
│   ├── config.yaml          # Configuración principal
│   ├── keywords.yaml        # Palabras clave para filtrado (recarga en caliente)
│   ├── scan.yaml            # GSSI y scan list activos en el radio (modificable via API)
│   ├── grupos.yaml          # Semilla inicial de grupos y scan lists (solo primer arranque)
│   └── nginx.conf           # Configuración nginx (proxy inverso TLS)
├── data/
│   ├── audio/               # Grabaciones .flac
│   └── db/
│       └── schema.sql       # DDL de PostgreSQL (llamadas + grupos + scan lists)
├── logs/                    # Logs de la aplicación
├── scripts/
│   ├── setup.sh                          # Instalación completa
│   ├── setup_nginx.sh                    # Instalación HTTPS con nginx
│   ├── migrate_grupos.sql                # Migración para instalaciones existentes
│   ├── hash_password.py                  # Generador de hash bcrypt
│   ├── start.sh                          # Arranque del daemon
│   └── tetra-monitor.service.template    # Plantilla unit file systemd
├── Makefile                 # Atajos para operaciones comunes
└── src/
    ├── main.py              # Punto de entrada (daemon + API en un solo proceso)
    ├── app_state.py         # Contenedor de dependencias compartidas
    ├── api/
    │   └── api.py           # API REST (FastAPI + JWT + rate limiting)
    ├── audio/
    │   ├── audio_buffer.py  # Captura y grabación de audio
    │   └── audio_cleanup.py # Limpieza automática de ficheros FLAC
    ├── core/
    │   ├── logger.py        # Logger centralizado
    │   ├── radio_config.py  # Config activa del radio (GSSI + scan list, mtime IPC)
    │   └── stt_processor.py # Transcripción con Whisper
    ├── db/
    │   ├── pool.py          # ThreadedConnectionPool compartido
    │   ├── llamadas.py      # Queries sobre la tabla llamadas
    │   └── grupos.py        # Catálogo de grupos y scan lists
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
# Hash bcrypt de la contraseña — genera con: make set-password
API_PASSWORD_HASH=$2b$12$...
```

> `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` solo son obligatorias si `telegram.enabled: true` en `config.yaml`.

### 3. Ejecutar el setup
El script instala automáticamente Python, PostgreSQL, ffmpeg y las dependencias Python, pre-descarga el modelo Whisper y aplica el schema de base de datos. Al final pregunta si instalar HTTPS con nginx:
```bash
make setup
```

### 4. Configurar la contraseña de la API
```bash
make set-password
```
El script pide la contraseña dos veces, genera el hash bcrypt y lo escribe directamente en `.env`.

### 5. (Opcional) Personalizar el catálogo de grupos
Edita `config/grupos.yaml` antes del primer arranque para definir los GSSIs y scan lists de tu red. En el primer arranque se cargan automáticamente en la BD. A partir de entonces el catálogo se gestiona directamente desde la BD (via API o DBeaver).

```yaml
grupos:
  - gssi: 36001
    nombre: "Operaciones"
    descripcion: "Canal principal"
  - gssi: 36002
    nombre: "Emergencias"

scan_lists:
  - nombre: "ListaScan1"
    grupos: [36001, 36002]
```

#### Migración desde una instalación existente
Si ya tienes el sistema instalado y quieres añadir las tablas de grupos:
```bash
psql -U $DB_USER -d tetra -f scripts/migrate_grupos.sql
```

---

## Arranque
```bash
make start
```

El daemon PEI y la API REST arrancan juntos en el mismo proceso. La API queda disponible en `http://raspberrypi:8000` (o `https://raspberrypi` si se instaló nginx).

---

## Makefile
```bash
make setup              # Instala dependencias y prepara el entorno
make setup-https        # Instala nginx con TLS (certificado autofirmado)
make set-password       # Genera hash bcrypt y lo guarda en .env
make start              # Arranca el monitor en primer plano
make stop               # Detiene el servicio systemd
make restart            # Reinicia el servicio systemd
make status             # Muestra el estado del servicio systemd
make logs               # Muestra los logs en tiempo real (journalctl)
make logs-file          # Muestra los logs en tiempo real (fichero local)
make install-service    # Instala tetra-monitor como servicio systemd
make uninstall-service  # Elimina el servicio systemd
make update             # git pull + reinicia el servicio si está activo
```

---

## HTTPS (opcional)
Para exponer la API con TLS usando nginx como proxy inverso:
```bash
make setup-https
```
Genera un certificado autofirmado RSA 4096 bits con validez de 10 años en `/etc/ssl/tetra-monitor/`. La API interna sigue corriendo en `localhost:8000`; nginx escucha en el puerto 443 y redirige HTTP→HTTPS automáticamente.

Sin nginx la API funciona igualmente en HTTP en el puerto 8000.

---

## Systemd (producción)
Para que el daemon arranque automáticamente con la RPi y se reinicie si falla:
```bash
make install-service
sudo systemctl start tetra-monitor
```

`make install-service` genera el unit file con el usuario actual y la ruta del proyecto sin necesidad de editar nada a mano.

```bash
make logs       # logs en tiempo real (journalctl)
make logs-file  # logs en tiempo real (fichero local)
make status     # estado del servicio
make restart    # reiniciar
make stop       # parar
```

---

## Seguridad

| Capa | Mecanismo |
|---|---|
| Autenticación | JWT (access token 1h) + refresh token (7 días, rotación) |
| Contraseña | Hash bcrypt almacenado en `.env` — nunca en texto plano |
| Rate limiting | 5 req/min en login, 30–60 req/min en el resto |
| Transporte | HTTPS con nginx (TLS 1.2/1.3, HSTS) — opcional |
| Comandos AT | Validación regex antes de enviar a la radio |
| Logs | Sin credenciales — username truncado a 32 chars |

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
Todos los endpoints (excepto `/health` y `/auth/*`) requieren autenticación JWT.

### Obtener token
```bash
curl -X POST http://raspberrypi:8000/auth/token \
  -d "username=admin&password=tu_password"
```
Respuesta:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "a3f...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Endpoints

| Método | Endpoint | Auth | Descripción |
|---|---|---|---|
| `GET` | `/health` | No | Healthcheck público |
| `POST` | `/auth/token` | No | Login — obtener access + refresh token |
| `POST` | `/auth/refresh` | No | Renovar access token con refresh token |
| `POST` | `/auth/logout` | No | Invalidar refresh token |
| `GET` | `/calls` | Sí | Listar llamadas (params: `limit`, `offset`, `gssi`, `ssi`, `texto`) |
| `GET` | `/calls/{id}` | Sí | Detalle de una llamada |
| `GET` | `/radio-config` | Sí | Ver GSSI y scan list activos en el radio |
| `POST` | `/radio-config/gssi` | Sí | Cambiar GSSI activo en el radio |
| `POST` | `/radio-config/scan-list` | Sí | Cambiar scan list activa en el radio |
| `GET` | `/groups` | Sí | Listar catálogo de grupos (param: `solo_activos`) |
| `GET` | `/groups/{gssi}` | Sí | Detalle de un grupo |
| `POST` | `/groups` | Sí | Crear o actualizar un grupo (upsert) |
| `GET` | `/scan-lists` | Sí | Listar scan lists con grupos anidados |

### Ejemplos
```bash
TOKEN=$(curl -s -X POST http://raspberrypi:8000/auth/token \
  -d "username=admin&password=tu_password" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Listar llamadas con filtro
curl -H "Authorization: Bearer $TOKEN" \
  "http://raspberrypi:8000/calls?limit=10&gssi=36001"

# Cambiar GSSI activo en el radio
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gssi": "36001"}' \
  http://raspberrypi:8000/radio-config/gssi

# Listar catálogo de grupos
curl -H "Authorization: Bearer $TOKEN" \
  http://raspberrypi:8000/groups

# Crear o actualizar un grupo
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"gssi": 36003, "nombre": "Logística", "descripcion": "Canal logístico", "activo": true}' \
  http://raspberrypi:8000/groups

# Ver scan lists con sus grupos
curl -H "Authorization: Bearer $TOKEN" \
  http://raspberrypi:8000/scan-lists
```

---

## Arquitectura
El sistema corre en **un único proceso** con dos componentes concurrentes:

- **Daemon PEI** — escucha la radio por puerto serie, graba audio, transcribe y alerta
- **API REST** — corre en un hilo separado, expone endpoints para consultar llamadas y modificar la configuración

La comunicación entre ambos se hace a través de `config/scan.yaml`. Cuando la API actualiza el GSSI o la scan list activa, escribe en el fichero. El daemon comprueba el `mtime` cada 5 segundos y aplica los cambios a la radio si detecta modificaciones. Lo mismo aplica a `config/keywords.yaml`, que también se recarga en caliente.

El **catálogo de grupos** (`grupos`, `scan_lists`, `scan_list_grupos`) vive en PostgreSQL y se usa para enriquecer las llamadas con el nombre del grupo. En el primer arranque se puede poblar desde `config/grupos.yaml` de forma automática; a partir de entonces se gestiona directamente en BD.

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
