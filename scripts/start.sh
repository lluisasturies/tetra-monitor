#!/bin/bash
# Arranque manual del proyecto

source venv/bin/activate

echo "Iniciando demonio PEI y grabación selectiva..."
python3 src/pei_daemon.py &
PID=$!
echo "PID: $PID"