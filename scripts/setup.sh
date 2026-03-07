#!/bin/bash
set -e  # salir si cualquier comando falla

echo "==============================="
echo "  TETRA Monitor — Instalación"
echo "==============================="

# ---------------------------
# Actualizar sistema
# ---------------------------
echo ""
echo "[1/6] Actualizando sistema..."
sudo apt update && sudo apt upgrade -y

# ---------------------------
# Instalar dependencias del sistema
# ---------------------------
echo ""
echo "[2/6] Instalando dependencias del sistema..."
sudo apt install -y \
    python3-pip python3-venv git build-essential \
    libsndfile1 ffmpeg libportaudio2 libportaudiocpp0 portaudio19-dev

# ---------------------------
# Instalar PostgreSQL
# ---------------------------
echo ""
echo "[3/6] Instalando PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib

# Leer credenciales del .env si existe
ENV_FILE="$(dirname "$0")/../.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
    echo "Credenciales cargadas desde .env"
else
    echo "AVISO: No se encontró .env — usando valores por defecto."
    echo "       Copia .env.example a .env y rellena tus credenciales antes de continuar."
    DB_USER=${DB_USER:-piuser}
    DB_PASSWORD=${DB_PASSWORD:-changeme}
fi

sudo -u postgres psql -c "CREATE USER ${DB_USER} WITH PASSWORD '${DB_PASSWORD}';" 2>/dev/null || echo "Usuario ${DB_USER} ya existe, continuando..."
sudo -u postgres psql -c "CREATE DATABASE tetra OWNER ${DB_USER};" 2>/dev/null || echo "Base de datos tetra ya existe, continuando..."
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE tetra TO ${DB_USER};" 2>/dev/null || echo "Privilegios al usuario ya dados, continuando..."

# ---------------------------
# Crear entorno virtual
# ---------------------------
echo ""
echo "[4/6] Creando entorno virtual..."
python3 -m venv ~/tetra-monitor/venv

# ---------------------------
# Instalar dependencias Python (usando pip del venv directamente)
# ---------------------------
echo ""
echo "[5/6] Instalando dependencias Python..."
~/tetra-monitor/venv/bin/pip install --upgrade pip
~/tetra-monitor/venv/bin/pip install \
    fastapi uvicorn psycopg2-binary \
    sounddevice soundfile \
    pyyaml requests \
    openai-whisper \
    pyserial \
    numpy \
    python-dotenv

# ---------------------------
# Crear estructura de carpetas
# ---------------------------
echo ""
echo "[6/6] Creando estructura de carpetas..."
mkdir -p ~/tetra-monitor/data/audio
mkdir -p ~/tetra-monitor/logs

# ---------------------------
# Aplicar esquema de BD
# ---------------------------
SCHEMA_PATH="$(dirname "$0")/../data/db/schema.sql"
if [ -f "$SCHEMA_PATH" ]; then
    echo "Aplicando esquema de base de datos..."
    sudo -u postgres psql -d tetra -f "$SCHEMA_PATH"
    echo "Esquema aplicado correctamente"
else
    echo "AVISO: No se encontró schema.sql en $SCHEMA_PATH"
fi

echo ""
echo "==============================="
echo "  Instalación completada ✓"
echo "  Recuerda configurar tu .env"
echo "==============================="
