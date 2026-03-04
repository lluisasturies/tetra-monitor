#!/bin/bash
# Script de instalación para Raspberry Pi 5

# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar dependencias básicas
sudo apt install -y python3-pip python3-venv git build-essential libsndfile1 ffmpeg

# Instalar PostgreSQL
sudo apt install -y postgresql postgresql-contrib
sudo -u postgres psql -c "CREATE USER piuser WITH PASSWORD 'pipassword';"
sudo -u postgres psql -c "CREATE DATABASE tetra OWNER piuser;"

# Crear entorno virtual
python3 -m venv venv
source venv/bin/activate

# Instalar dependencias Python
pip install --upgrade pip
pip install fastapi uvicorn psycopg2-binary sounddevice soundfile pyyaml requests whisper

# Crear carpetas de datos y logs
mkdir -p data/audio
mkdir -p data/db
mkdir -p logs

echo "Instalación completada. Activa el entorno con: source venv/bin/activate"