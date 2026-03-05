#!/bin/bash
# Arranque manual del proyecto

cd src

echo "Iniciando demonio PEI y grabación selectiva..."
python3 pei_daemon.py &
PID=$!
echo "PID: $PID"