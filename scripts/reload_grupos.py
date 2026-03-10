#!/usr/bin/env python3
"""
recarga el catálogo de grupos, carpetas y scan lists desde config/grupos.yaml,
reemplazando completamente los datos existentes en la BD.

Uso:
    make reload-grupos
    # o directamente:
    python3 scripts/reload_grupos.py [--dry-run]

Opciones:
    --dry-run   Muestra lo que se cargaría sin tocar la BD.
    --yes       Omite la confirmación interactiva.
"""

import os
import sys
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import yaml


def _load_yaml(path: Path) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _preview(data: dict):
    grupos     = data.get("grupos", [])
    carpetas   = data.get("carpetas", [])
    scan_lists = data.get("scan_lists", [])

    print(f"\n  Grupos     : {len(grupos)}")
    for g in grupos:
        print(f"    - {g['gssi']:>8}  {g['nombre']}")

    print(f"\n  Carpetas   : {len(carpetas)}")
    for c in carpetas:
        print(f"    - {c['nombre']}  ({len(c.get('grupos', []))} grupos)")

    print(f"\n  Scan lists : {len(scan_lists)}")
    for sl in scan_lists:
        print(f"    - {sl['nombre']}  ({len(sl.get('grupos', []))} grupos)")
    print()


def _reload(data: dict, cfg: dict):
    from db.pool import DBPool
    from psycopg2.extras import execute_values

    pool = DBPool(
        host=cfg["database"]["host"],
        port=cfg["database"]["port"],
        dbname=cfg["database"]["dbname"],
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
    )

    grupos     = data.get("grupos", [])
    carpetas   = data.get("carpetas", [])
    scan_lists = data.get("scan_lists", [])

    conn = pool.getconn()
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # --- Grupos: upsert (nunca borra, para no romper FKs de llamadas)
            for g in grupos:
                cur.execute(
                    """
                    INSERT INTO grupos (gssi, nombre)
                    VALUES (%s, %s)
                    ON CONFLICT (gssi) DO UPDATE SET nombre = EXCLUDED.nombre
                    """,
                    (g["gssi"], g["nombre"])
                )
            print(f"  ✓ {len(grupos)} grupos sincronizados")

            # --- Carpetas: reemplazar completamente
            cur.execute("DELETE FROM carpeta_grupos")
            cur.execute("DELETE FROM carpetas")
            for orden_c, c in enumerate(carpetas):
                cur.execute(
                    "INSERT INTO carpetas (nombre, orden) VALUES (%s, %s) RETURNING id",
                    (c["nombre"], c.get("orden", orden_c))
                )
                carpeta_id = cur.fetchone()[0]
                for orden_g, entry in enumerate(c.get("grupos", [])):
                    gssi        = entry if isinstance(entry, int) else entry["gssi"]
                    orden_grupo = orden_g if isinstance(entry, int) else entry.get("orden", orden_g)
                    cur.execute(
                        "INSERT INTO carpeta_grupos (carpeta_id, gssi, orden) VALUES (%s, %s, %s)",
                        (carpeta_id, gssi, orden_grupo)
                    )
            print(f"  ✓ {len(carpetas)} carpetas sincronizadas")

            # --- Scan lists: reemplazar completamente
            cur.execute("DELETE FROM scan_list_grupos")
            cur.execute("DELETE FROM scan_lists")
            for sl in scan_lists:
                cur.execute(
                    "INSERT INTO scan_lists (nombre) VALUES (%s) RETURNING id",
                    (sl["nombre"],)
                )
                sl_id = cur.fetchone()[0]
                for gssi in sl.get("grupos", []):
                    cur.execute(
                        "INSERT INTO scan_list_grupos (scan_list_id, gssi) VALUES (%s, %s)",
                        (sl_id, gssi)
                    )
            print(f"  ✓ {len(scan_lists)} scan lists sincronizadas")

        conn.commit()
        print("\n  Recarga completada.\n")

    except Exception as e:
        conn.rollback()
        print(f"\n  ERROR: {e}\n", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.autocommit = True
        pool.putconn(conn)
        pool.closeall()


def main():
    parser = argparse.ArgumentParser(description="Recarga el catálogo de grupos desde grupos.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Muestra los cambios sin aplicarlos")
    parser.add_argument("--yes",     action="store_true", help="Omite la confirmación interactiva")
    args = parser.parse_args()

    grupos_path = PROJECT_ROOT / "config" / "grupos.yaml"
    config_path = PROJECT_ROOT / "config" / "config.yaml"

    if not grupos_path.exists():
        print(f"ERROR: no se encontró {grupos_path}", file=sys.stderr)
        sys.exit(1)
    if not config_path.exists():
        print(f"ERROR: no se encontró {config_path}", file=sys.stderr)
        sys.exit(1)

    data = _load_yaml(grupos_path)
    cfg  = _load_yaml(config_path)

    print("\nContenido de grupos.yaml:")
    _preview(data)

    if args.dry_run:
        print("  [dry-run] No se ha modificado nada.\n")
        sys.exit(0)

    if not args.yes:
        resp = input("  ¿Aplicar cambios en la BD? Los grupos existentes se actualizarán\n"
                     "  y carpetas/scan_lists se reemplazarán completamente. [s/N] ").strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            print("  Cancelado.\n")
            sys.exit(0)

    print()
    _reload(data, cfg)


if __name__ == "__main__":
    main()
