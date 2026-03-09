#!/usr/bin/env python3
"""
Utilidad para generar el hash bcrypt de la contraseña de la API
y escribirlo directamente en el .env.

Uso directo:  python3 scripts/hash_password.py
Uso con .env: python3 scripts/hash_password.py --env /ruta/.env
Desde make:   make set-password
"""
import argparse
import getpass
import re
import sys
from pathlib import Path

try:
    import bcrypt
except ImportError:
    print("ERROR: bcrypt no está instalado. Ejecuta primero: make setup")
    sys.exit(1)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def update_env(env_path: Path, hashed: str):
    """Sustituye o añade API_PASSWORD_HASH en el .env. Elimina API_PASSWORD si existe."""
    content = env_path.read_text() if env_path.exists() else ""

    # Eliminar API_PASSWORD (texto plano) si existe
    content = re.sub(r'^API_PASSWORD=.*$', '', content, flags=re.MULTILINE)

    # Sustituir o añadir API_PASSWORD_HASH
    new_line = f"API_PASSWORD_HASH={hashed}"
    if re.search(r'^API_PASSWORD_HASH=', content, flags=re.MULTILINE):
        content = re.sub(r'^API_PASSWORD_HASH=.*$', new_line, content, flags=re.MULTILINE)
    else:
        content = content.rstrip('\n') + f"\n{new_line}\n"

    # Limpiar líneas vacías múltiples
    content = re.sub(r'\n{3,}', '\n\n', content)

    env_path.write_text(content)
    print(f"[OK] .env actualizado: {env_path}")


def main():
    parser = argparse.ArgumentParser(description="Genera hash bcrypt para API_PASSWORD_HASH")
    parser.add_argument("--env", type=Path, help="Ruta al fichero .env para actualizarlo automáticamente")
    args = parser.parse_args()

    print()
    print("=== Configurar contraseña de la API ===")
    print()

    password = getpass.getpass("Nueva contraseña: ")
    confirm  = getpass.getpass("Confirma la contraseña: ")

    if password != confirm:
        print("ERROR: Las contraseñas no coinciden.")
        sys.exit(1)

    if len(password) < 8:
        print("AVISO: La contraseña tiene menos de 8 caracteres.")

    if len(password.encode()) > 72:
        print("ERROR: La contraseña no puede superar 72 bytes (limitación de bcrypt).")
        sys.exit(1)

    hashed = hash_password(password)

    if args.env:
        update_env(args.env, hashed)
        print("Contraseña configurada. Ahora puedes ejecutar: make start")
    else:
        print()
        print("Hash generado:")
        print(f"  {hashed}")
        print()
        print("Añade esta línea a tu .env:")
        print(f"  API_PASSWORD_HASH={hashed}")
    print()


if __name__ == "__main__":
    main()
