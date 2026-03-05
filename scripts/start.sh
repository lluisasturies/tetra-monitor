#!/bin/bash
# Arranque manual del proyecto

source ../venv/bin/activate
cd src

echo "Iniciando demonio PEI y grabación selectiva..."
python3 pei_daemon.py &
PID=$!
echo "PID: $PID"