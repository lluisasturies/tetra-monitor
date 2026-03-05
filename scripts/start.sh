#!/bin/bash

# Ruta absoluta del entorno virtual
VENV_PATH=~/tetra-monitor/venv

# Activar el entorno
source $VENV_PATH/bin/activate

echo "Iniciando demonio PEI y grabación selectiva..."
python3 src/pei_daemon.py &
PID=$!
echo "PID: $PID"