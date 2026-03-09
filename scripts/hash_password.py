#!/usr/bin/env python3
"""
Utilidad para generar el hash bcrypt de la contraseña de la API.
Uso: python3 scripts/hash_password.py

Copia el resultado en tu .env como:
  API_PASSWORD_HASH=<hash>
"""
import getpass
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def main():
    print()
    print("=== Generador de hash bcrypt para API_PASSWORD ===")
    print()
    password = getpass.getpass("Introduce la contraseña: ")
    confirm  = getpass.getpass("Confirma la contraseña:  ")

    if password != confirm:
        print("ERROR: Las contraseñas no coinciden.")
        raise SystemExit(1)

    if len(password) < 8:
        print("AVISO: La contraseña tiene menos de 8 caracteres.")

    hashed = pwd_context.hash(password)
    print()
    print("Hash generado:")
    print(f"  {hashed}")
    print()
    print("Añade esta línea a tu .env:")
    print(f"  API_PASSWORD_HASH={hashed}")
    print()

if __name__ == "__main__":
    main()
