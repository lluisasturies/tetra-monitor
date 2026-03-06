#!/bin/bash

# Ruta absoluta del entorno virtual
VENV_PATH=~/tetra-monitor/venv

# Activar el entorno
source $VENV_PATH/bin/activate

echo "Iniciando monitor PEI y grabación selectiva..."
python3 src/main.py &
PID=$!
echo "PID: $PID"