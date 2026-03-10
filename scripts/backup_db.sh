#!/usr/bin/env bash
# =============================================================================
# backup_db.sh — Volcado de la BD PostgreSQL de tetra-monitor
#
# Uso:
#   make backup-db
#   # o directamente:
#   bash scripts/backup_db.sh
#
# Genera un fichero comprimido en data/backups/ con la fecha y hora actuales.
# Mantiene los últimos 30 backups y elimina los más antiguos automáticamente.
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
ENV_FILE="$PROJECT_ROOT/.env"
BACKUP_DIR="$PROJECT_ROOT/data/backups"
KEEP=30

# Cargar variables de entorno
if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: no se encontró .env en $PROJECT_ROOT" >&2
    exit 1
fi

export $(grep -v '^#' "$ENV_FILE" | grep -E '^(DB_USER|DB_PASSWORD)=' | xargs)

# Leer config.yaml para host/port/dbname
CONFIG_FILE="$PROJECT_ROOT/config/config.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "ERROR: no se encontró config/config.yaml" >&2
    exit 1
fi

DB_HOST=$(grep 'host:' "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
DB_PORT=$(grep 'port:' "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')
DB_NAME=$(grep 'dbname:' "$CONFIG_FILE" | head -1 | awk '{print $2}' | tr -d '"')

DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}
DB_NAME=${DB_NAME:-tetra}

# Crear directorio de backups si no existe
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT="$BACKUP_DIR/tetra_${TIMESTAMP}.sql.gz"

echo "Realizando backup de '$DB_NAME' en $DB_HOST:$DB_PORT..."

PGPASSWORD="$DB_PASSWORD" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --no-password \
    | gzip > "$OUTPUT"

SIZE=$(du -sh "$OUTPUT" | cut -f1)
echo "✓ Backup guardado: $OUTPUT ($SIZE)"

# Eliminar backups más antiguos manteniendo solo los últimos $KEEP
COUNT=$(ls -1 "$BACKUP_DIR"/tetra_*.sql.gz 2>/dev/null | wc -l)
if [ "$COUNT" -gt "$KEEP" ]; then
    EXCESS=$(( COUNT - KEEP ))
    ls -1t "$BACKUP_DIR"/tetra_*.sql.gz | tail -"$EXCESS" | xargs rm -f
    echo "✓ Eliminados $EXCESS backups antiguos (se mantienen los últimos $KEEP)"
fi
