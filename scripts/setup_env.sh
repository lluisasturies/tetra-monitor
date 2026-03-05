#!/bin/bash
# Script de instalación

# Actualizar sistema
echo "Actualizando sistema..."
sudo apt update && sudo apt upgrade -y

# Instalar dependencias básicas
echo "Instalando dependencias basicas..."
sudo apt install -y python3-pip python3-venv git build-essential libsndfile1 ffmpeg

# Instalar PostgreSQL
echo "Instalando PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib
sudo -u postgres psql -c "CREATE USER piuser WITH PASSWORD 'pipassword';"
sudo -u postgres psql -c "CREATE DATABASE tetra OWNER piuser;"

# Crear entorno virtual
echo "Creando entorno virtual..."
python3 -m venv ~/tetra-monitor/venv

# Instalar dependencias Python
echo "Instalando dependencias de Python..."
pip install --upgrade pip
pip install fastapi uvicorn psycopg2-binary sounddevice soundfile pyyaml requests whisper

# Crear carpetas de datos y logs
echo "Creando estructura de carpetas necesaria..."
mkdir -p data/audio
mkdir -p logs

echo "Instalación completada."