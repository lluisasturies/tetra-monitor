#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"
ENV_FILE="$PROJECT_ROOT/.env"

echo "==============================="
echo "  TETRA Monitor — Arranque"
echo "==============================="

# ---------------------------
# Cargar variables de entorno
# ---------------------------
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
    echo "Variables de entorno cargadas desde .env"
else
    echo "ERROR: No se encontró .env en $ENV_FILE"
    echo "       Copia .env.example a .env y rellena tus credenciales."
    exit 1
fi

# ---------------------------
# Comprobar entorno virtual
# ---------------------------
if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "ERROR: Entorno virtual no encontrado en $VENV_PATH"
    echo "       Ejecuta primero: scripts/setup.sh"
    exit 1
fi

source "$VENV_PATH/bin/activate"
echo "Entorno virtual activado: $VENV_PATH"

# ---------------------------
# Arrancar
# ---------------------------
echo "Iniciando TETRA Monitor..."
cd "$PROJECT_ROOT/src"
exec python3 main.py  # exec reemplaza el proceso bash — señales llegan directamente a Python
