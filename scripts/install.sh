#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"
REQUIREMENTS="$PROJECT_ROOT/requirements.txt"
SCHEMA="$PROJECT_ROOT/data/db/schema.sql"
CONFIG="$PROJECT_ROOT/config/config.yaml"
ENV_FILE="$PROJECT_ROOT/.env"
REAL_USER="${SUDO_USER:-$USER}"

echo "==============================="
echo "  TETRA Monitor - Instalacion"
echo "==============================="

# ---------------------------
# Comprobar que corremos con sudo
# ---------------------------
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: Ejecuta el install con sudo:"
    echo "       sudo bash scripts/install.sh"
    exit 1
fi

# ---------------------------
# Actualizar lista de paquetes
# ---------------------------
echo "Actualizando lista de paquetes..."
apt update -qq

# ---------------------------
# Python 3
# ---------------------------
if ! command -v python3 &> /dev/null; then
    echo "[INSTALAR] Python 3..."
    apt install -y python3 python3-pip python3-venv
    echo "  -> Python $(python3 --version) instalado"
else
    echo "[OK] Python $(python3 --version)"
fi

if ! python3 -m venv --help &> /dev/null; then
    echo "[INSTALAR] python3-venv..."
    apt install -y python3-venv
fi

# ---------------------------
# PostgreSQL
# ---------------------------
if ! command -v psql &> /dev/null; then
    echo "[INSTALAR] PostgreSQL..."
    apt install -y postgresql postgresql-client libpq-dev
    systemctl enable postgresql
    systemctl start postgresql
    echo "  -> PostgreSQL instalado y arrancado"
else
    echo "[OK] PostgreSQL $(psql --version | awk '{print $3}')"
    if ! dpkg -s libpq-dev &> /dev/null; then
        echo "[INSTALAR] libpq-dev..."
        apt install -y libpq-dev --no-install-recommends -qq
    fi
    if ! systemctl is-active --quiet postgresql; then
        echo "[ARRANCAR] PostgreSQL..."
        systemctl start postgresql
    fi
fi

# ---------------------------
# ffmpeg
# ---------------------------
if ! command -v ffmpeg &> /dev/null; then
    echo "[INSTALAR] ffmpeg..."
    apt install -y ffmpeg
    echo "  -> ffmpeg instalado"
else
    echo "[OK] ffmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')"
fi

# ---------------------------
# Entorno virtual
# ---------------------------
if [ ! -f "$VENV_PATH/bin/activate" ]; then
    echo "[CREAR] Entorno virtual en $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
else
    echo "[OK] Entorno virtual existe"
fi

source "$VENV_PATH/bin/activate"

# ---------------------------
# Dependencias Python
# ---------------------------
if [ ! -f "$REQUIREMENTS" ]; then
    echo "ERROR: No se encontro requirements.txt en $REQUIREMENTS"
    exit 1
fi

echo "[PIP] Actualizando pip, setuptools y wheel..."
pip install --upgrade pip setuptools wheel --quiet

echo "[PIP] Instalando/actualizando dependencias desde requirements.txt..."
pip install -r "$REQUIREMENTS" --quiet

echo "[PIP] Instalando paquete tetra-monitor..."
pip install "$PROJECT_ROOT" --quiet
echo "[OK] Dependencias Python al dia"

# ---------------------------
# Modelo Whisper
# ---------------------------
WHISPER_MODEL="base"
if [ -f "$CONFIG" ]; then
    WHISPER_MODEL=$(python3 -c "
import yaml
try:
    cfg = yaml.safe_load(open('$CONFIG'))
    print(cfg.get('stt', {}).get('model', 'base'))
except Exception:
    print('base')
")
fi

WHISPER_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/whisper"
if [ -f "${WHISPER_CACHE}/${WHISPER_MODEL}.pt" ]; then
    echo "[OK] Modelo Whisper '$WHISPER_MODEL' ya descargado"
else
    echo "[DESCARGAR] Modelo Whisper '$WHISPER_MODEL'..."
    python3 -c "import whisper; whisper.load_model('$WHISPER_MODEL')"
    echo "  -> Modelo '$WHISPER_MODEL' descargado"
fi

# ---------------------------
# Directorios necesarios
# ---------------------------
DIRS_CREATED=0
for dir in "$PROJECT_ROOT/data/audio" "$PROJECT_ROOT/logs"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        DIRS_CREATED=1
    fi
done
chown -R "$REAL_USER:$REAL_USER" "$PROJECT_ROOT/data" "$PROJECT_ROOT/logs"
if [ "$DIRS_CREATED" -eq 1 ]; then
    echo "[CREAR] Directorios data/audio y logs creados"
else
    echo "[OK] Directorios data/audio y logs existen"
fi

# ---------------------------
# PostgreSQL: usuario, BD y schema
# ---------------------------
if [ ! -f "$ENV_FILE" ]; then
    echo ""
    echo "[AVISO] No se encontro .env - omitiendo configuracion de BD."
    echo "        Copia .env.example a .env, rellena las credenciales y vuelve a ejecutar:"
    echo "        sudo bash scripts/install.sh"
else
    set -a; source "$ENV_FILE"; set +a

    # Crear usuario BD si no existe
    if sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        echo "[OK] Usuario PostgreSQL '$DB_USER' existe"
    else
        echo "[CREAR] Usuario PostgreSQL '$DB_USER'..."
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
    fi

    # Crear base de datos si no existe
    if sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='tetra'" | grep -q 1; then
        echo "[OK] Base de datos 'tetra' existe"
    else
        echo "[CREAR] Base de datos 'tetra'..."
        sudo -u postgres psql -c "CREATE DATABASE tetra OWNER $DB_USER;"
    fi

    # Aplicar schema (idempotente: IF NOT EXISTS en todas las tablas)
    if [ ! -f "$SCHEMA" ]; then
        echo "ERROR: No se encontro schema.sql en $SCHEMA"
        exit 1
    fi
    echo "[SQL] Aplicando schema (idempotente)..."
    sed "s|@@DB_USER@@|$DB_USER|g" "$SCHEMA" > /tmp/tetra_schema.sql
    chmod 644 /tmp/tetra_schema.sql
    sudo -u postgres psql -d tetra -f /tmp/tetra_schema.sql -q
    rm -f /tmp/tetra_schema.sql
    echo "[OK] Schema aplicado"

    # ---------------------------
    # Usuario admin de la API
    # Solo se pregunta si API_USER no esta definido en .env (instalacion limpia).
    # En actualizaciones se omite silenciosamente.
    # ---------------------------
    if [ -z "${API_USER:-}" ]; then
        echo ""
        echo "--- Configuracion del usuario admin de la API ---"
        echo "Define el usuario y contrasena con los que accederas a la API."
        echo ""

        # Nombre de usuario
        read -r -p "Nombre de usuario admin [admin]: " ADMIN_USER
        ADMIN_USER="${ADMIN_USER:-admin}"

        # Contrasena con confirmacion (oculta con read -s)
        while true; do
            read -r -s -p "Contrasena (min. 8 caracteres): " ADMIN_PASS
            echo ""
            if [ ${#ADMIN_PASS} -lt 8 ]; then
                echo "  ERROR: La contrasena debe tener al menos 8 caracteres."
                continue
            fi
            read -r -s -p "Confirma la contrasena: " ADMIN_PASS2
            echo ""
            if [ "$ADMIN_PASS" != "$ADMIN_PASS2" ]; then
                echo "  ERROR: Las contrasenas no coinciden."
                continue
            fi
            break
        done

        # Generar hash bcrypt con Python (bcrypt ya instalado en el venv)
        ADMIN_HASH=$(python3 - "$ADMIN_PASS" << 'PYEOF'
import bcrypt, sys
pw = sys.argv[1].encode()
if len(pw) > 72:
    print('ERROR: La contrasena supera 72 bytes (limite bcrypt)', file=sys.stderr)
    sys.exit(1)
print(bcrypt.hashpw(pw, bcrypt.gensalt()).decode())
PYEOF
)

        # Escribir API_USER y API_PASSWORD_HASH en .env
        python3 - "$ADMIN_USER" "$ADMIN_HASH" "$ENV_FILE" << 'PYEOF'
import re, sys
from pathlib import Path

user     = sys.argv[1]
hashed   = sys.argv[2]
env_path = Path(sys.argv[3])
content  = env_path.read_text()

def set_var(text, key, value):
    line = f'{key}={value}'
    if re.search(rf'^{key}=', text, re.MULTILINE):
        return re.sub(rf'^{key}=.*$', line, text, flags=re.MULTILINE)
    return text.rstrip('\n') + f'\n{line}\n'

content = set_var(content, 'API_USER', user)
content = set_var(content, 'API_PASSWORD_HASH', hashed)
content = re.sub(r'\n{3,}', '\n\n', content)
env_path.write_text(content)
PYEOF

        echo "[OK] Usuario admin '$ADMIN_USER' configurado en .env"
    else
        echo "[OK] Usuario admin ya configurado ('${API_USER}') - omitiendo"
    fi
fi

# ---------------------------
# HTTPS (solo en instalacion limpia)
# ---------------------------
if ! command -v nginx &> /dev/null; then
    echo ""
    read -r -p "[?] Instalar HTTPS con nginx? (recomendado si la API es accesible desde fuera) [s/N]: " INSTALL_HTTPS
    if [[ "$INSTALL_HTTPS" =~ ^[sS]$ ]]; then
        bash "$SCRIPT_DIR/setup_nginx.sh"
    else
        echo "HTTPS omitido. Puedes instalarlo mas tarde con: make setup-https"
    fi
else
    echo "[OK] nginx ya instalado - omitiendo pregunta HTTPS"
fi

# ---------------------------
# Fin
# ---------------------------
echo ""
echo "==============================="
echo "  Instalacion completada"
echo "==============================="
echo ""
echo "Pasos siguientes:"
echo "  1. Revisa config/config.yaml y .env con tus valores reales"
echo "  2. Arranca con:  make start   o   bash scripts/start.sh"
echo ""
