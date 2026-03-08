#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"
REQUIREMENTS="$PROJECT_ROOT/requirements.txt"
SCHEMA="$PROJECT_ROOT/data/db/schema.sql"

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
# Comprobar .env
# ---------------------------
ENV_FILE="$PROJECT_ROOT/.env"
ENV_EXAMPLE="$PROJECT_ROOT/.env.example"

if [ ! -f "$ENV_FILE" ]; then
    if [ -f "$ENV_EXAMPLE" ]; then
        echo ""
        echo "AVISO: No existe .env — cópialo desde .env.example y rellena tus credenciales:"
        echo "       cp .env.example .env"
    else
        echo ""
        echo "AVISO: No existe .env. Créalo con las siguientes variables:"
        echo "       DB_USER, DB_PASSWORD, DB_NAME, DB_HOST, DB_PORT"
        echo "       TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, JWT_SECRET, API_KEY"
    fi
    echo "       El schema de BD no se aplicará hasta que exista .env"
else
    echo ".env encontrado"

    # ---------------------------
    # Aplicar schema de base de datos
    # ---------------------------
    if [ ! -f "$SCHEMA" ]; then
        echo "ERROR: No se encontró schema.sql en $SCHEMA"
        exit 1
    fi

    echo "Aplicando schema en PostgreSQL..."
    sudo -u postgres psql -f "$SCHEMA" \
        && echo "Schema aplicado correctamente" \
        || echo "AVISO: Error aplicando el schema — puede que ya esté aplicado."
fi

# ---------------------------
# Crear directorios necesarios
# ---------------------------
mkdir -p "$PROJECT_ROOT/data/audio"
mkdir -p "$PROJECT_ROOT/logs"
echo "Directorios data/audio y logs listos"

echo ""
echo "==============================="
echo "  Setup completado"
echo "  Arranca con: scripts/start.sh"
echo "==============================="