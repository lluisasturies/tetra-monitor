#!/bin/bash
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.."; pwd)"
CERT_DIR="/etc/ssl/tetra-monitor"
NGINX_CONF="/etc/nginx/sites-available/tetra-monitor"
NGINX_ENABLED="/etc/nginx/sites-enabled/tetra-monitor"

echo
echo "=================================="
echo "  TETRA Monitor — Setup HTTPS/Nginx"
echo "=================================="
echo

# --- Instalar nginx si no está ---
if ! command -v nginx &>/dev/null; then
    echo "[*] Instalando nginx..."
    sudo apt-get install -y nginx
else
    echo "[*] nginx ya instalado: $(nginx -v 2>&1)"
fi

# --- Generar certificado autofirmado ---
echo "[*] Generando certificado TLS autofirmado en $CERT_DIR..."
sudo mkdir -p "$CERT_DIR"
sudo openssl req -x509 -nodes -days 3650 \
    -newkey rsa:4096 \
    -keyout "$CERT_DIR/key.pem" \
    -out    "$CERT_DIR/cert.pem" \
    -subj   "/C=ES/ST=Asturias/O=TetraMonitor/CN=tetra-monitor" \
    -addext "subjectAltName=IP:127.0.0.1"
sudo chmod 600 "$CERT_DIR/key.pem"
sudo chmod 644 "$CERT_DIR/cert.pem"
echo "[OK] Certificado generado (válido 10 años)"

# --- Instalar configuración nginx ---
echo "[*] Instalando configuración nginx..."
sudo cp "$PROJECT_ROOT/config/nginx.conf" "$NGINX_CONF"

# Activar el site y desactivar el default
if [ ! -L "$NGINX_ENABLED" ]; then
    sudo ln -s "$NGINX_CONF" "$NGINX_ENABLED"
fi
if [ -L "/etc/nginx/sites-enabled/default" ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo "[*] Site 'default' de nginx desactivado"
fi

# --- Validar configuración ---
echo "[*] Validando configuración nginx..."
sudo nginx -t

# --- Reiniciar nginx ---
echo "[*] Reiniciando nginx..."
sudo systemctl enable nginx
sudo systemctl restart nginx

echo
echo "[OK] HTTPS activo en https://$(hostname -I | awk '{print $1}')"
echo "[INFO] Certificado autofirmado — el navegador mostrara una advertencia."
echo "[INFO] Para eliminarlo, usa Let's Encrypt si tienes dominio propio:"
echo "       sudo apt install certbot python3-certbot-nginx"
echo "       sudo certbot --nginx -d tu.dominio.com"
echo
