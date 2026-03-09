#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"
REQUIREMENTS="$PROJECT_ROOT/requirements.txt"
SCHEMA="$PROJECT_ROOT/data/db/schema.sql"
CONFIG="$PROJECT_ROOT/config/config.yaml"

echo "==============================="
echo "  TETRA Monitor — Setup"
echo "==============================="

# ---------------------------
# Comprobar que corremos con sudo
# ---------------------------
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Ejecuta el setup con sudo:"
    echo "       sudo bash scripts/setup.sh"
    exit 1
fi

# ---------------------------
# Actualizar sistema
# ---------------------------
echo "Actualizando lista de paquetes..."
apt update -qq

# ---------------------------
# Instalar Python 3 si no está
# ---------------------------
if ! command -v python3 &> /dev/null; then
    echo "Python 3 no encontrado. Instalando..."
    apt install -y python3 python3-pip python3-venv
    echo "Python $(python3 --version) instalado"
else
    echo "Python $(python3 --version) detectado"
fi

# Asegurarse de que python3-venv está disponible
if ! python3 -m venv --help &> /dev/null; then
    echo "Instalando python3-venv..."
    apt install -y python3-venv
fi

# ---------------------------
# Instalar PostgreSQL si no está
# ---------------------------
if ! command -v psql &> /dev/null; then
    echo "PostgreSQL no encontrado. Instalando..."
    apt install -y postgresql postgresql-client
    systemctl enable postgresql
    systemctl start postgresql
    echo "PostgreSQL instalado y arrancado"
else
    echo "PostgreSQL ya instalado ($(psql --version))"
    if ! systemctl is-active --quiet postgresql; then
        echo "Arrancando PostgreSQL..."
        systemctl start postgresql
    fi
fi

# ---------------------------
# Instalar ffmpeg (necesario para streaming)
# ---------------------------
if ! command -v ffmpeg &> /dev/null; then
    echo "ffmpeg no encontrado. Instalando..."
    apt install -y ffmpeg
    echo "ffmpeg instalado"
else
    echo "ffmpeg ya instalado"
fi

# ---------------------------
# Crear entorno virtual
# ---------------------------
if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "Creando entorno virtual en $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
else
    echo "Entorno virtual ya existe en $VENV_PATH"
fi

source "$VENV_PATH/bin/activate"
echo "Entorno virtual activado"

# ---------------------------
# Instalar dependencias Python
# ---------------------------
if [ ! -f "$REQUIREMENTS" ]; then
    echo "ERROR: No se encontró requirements.txt en $REQUIREMENTS"
    exit 1
fi

echo "Instalando dependencias desde requirements.txt..."
pip install --upgrade pip --quiet
pip install -r "$REQUIREMENTS"
echo "Dependencias instaladas correctamente"

# ---------------------------
# Pre-descargar modelo Whisper
# ---------------------------
WHISPER_MODEL="base"
if [ -f "$CONFIG" ] && command -v python3 &> /dev/null; then
    WHISPER_MODEL=$(python3 -c "
import yaml, sys
try:
    cfg = yaml.safe_load(open('$CONFIG'))
    print(cfg.get('stt', {}).get('model', 'base'))
except Exception:
    print('base')
")
fi

echo "Pre-descargando modelo Whisper '$WHISPER_MODEL'..."
p