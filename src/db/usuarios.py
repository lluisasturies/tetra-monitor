import secrets
import bcrypt
from datetime import datetime, timezone
from psycopg2.extras import RealDictCursor
from core.logger import logger
from db.pool import DBPool

# Roles validos -- en el mismo orden de menor a mayor privilegio
ROLES = ("viewer", "operator", "admin")


class UsuariosDB:
    """
    Capa de acceso a las tablas 'usuarios' y 'refresh_tokens'.

    Los refresh tokens se persisten en BD para que sobrevivan reinicios
    del proceso y puedan revocarse individualmente por usuario.
    """

    def __init__(self, pool: DBPool):
        self.pool = pool

    # ------------------------------------------------------------------
    # Usuarios
    # ------------------------------------------------------------------

    def crear(self, username: str, password: str, rol: str = "viewer",
              email: str | None = None) -> dict | None:
        """
        Inserta un nuevo usuario. Hashea la contrasena con bcrypt.
        Devuelve el dict del usuario creado, o None si el username/email ya existe.
        """
        if rol not in ROLES:
            logger.error(f"[UsuariosDB] Rol invalido: '{rol}'")
            return None
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO usuarios (username, email, password_hash, rol)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, username, email, rol, activo, created_at, last_login
                    """,
                    (username, email, pw_hash, rol),
                )
                row = cur.fetchone()
            conn.commit()
            logger.info(f"[UsuariosDB] Usuario creado: '{username}' (rol={rol})")
            return dict(row)
        except Exception as e:
            conn.rollback()
            # No logueamos la excepcion completa para no filtrar datos sensibles
            logger.warning(f"[UsuariosDB] No se pudo crear usuario '{username}': {e}")
            return None
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    def obtener_por_username(self, username: str) -> dict | None:
        """Devuelve el registro completo del usuario (incluye password_hash)."""
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM usuarios WHERE username = %s",
                    (username,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"[UsuariosDB] Error obteniendo usuario '{username}': {e}")
            return None
        finally:
            conn.rollback()
            self.pool.putconn(conn)

    def obtener_por_id(self, usuario_id: int) -> dict | None:
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, username, email, rol, activo, created_at, last_login
                    FROM usuarios WHERE id = %s
                    """,
                    (usuario_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"[UsuariosDB] Error obteniendo usuario id={usuario_id}: {e}")
            return None
        finally:
            conn.rollback()
            self.pool.putconn(conn)

    def listar(self) -> list[dict]:
        """Devuelve todos los usuarios sin el campo password_hash."""
        conn = self.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, username, email, rol, activo, created_at, last_login
                    FROM usuarios
                    ORDER BY id
                    """
                )
                return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"[UsuariosDB] Error listando usuarios: {e}")
            return []
        finally:
            conn.rollback()
            self.pool.putconn(conn)

    def actualizar(self, usuario_id: int, **campos) -> dict | None:
        """
        Actualiza campos arbitrarios de un usuario.
        Campos permitidos: username, email, rol, activo, password (se hashea).
        Devuelve el usuario actualizado, o None si no existe o hubo error.
        """
        CAMPOS_PERMITIDOS = {"username", "email", "rol", "activo", "password"}
        updates: dict[str, object] = {}

        for k, v in campos.items():
            if k not in CAMPOS_PERMITIDOS:
                logger.warning(f"[UsuariosDB] Campo ignorado en actualizar: '{k}'")
                continue
            if k == "password":
                updates["password_hash"] = bcrypt.hashpw(
                    str(v).encode(), bcrypt.gensalt()
                ).decode()
            elif k == "rol" and v not in ROLES:
                logger.error(f"[UsuariosDB] Rol invalido en actualizar: '{v}'")
                return None
            else:
                updates[k] = v

        if not updates:
            return self.obtener_por_id(usuario_id)

        cols   = ", ".join(f"{k} = %s" for k in updates)
        values = list(updates.values()) + [usuario_id]

        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    UPDATE usuarios SET {cols}
                    WHERE id = %s
                    RETURNING id, username, email, rol, activo, created_at, last_login
                    """,
                    values,
                )
                row = cur.fetchone()
            conn.commit()
            return dict(row) if row else None
        except Exception as e:
            conn.rollback()
            logger.error(f"[UsuariosDB] Error actualizando usuario id={usuario_id}: {e}")
            return None
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    def marcar_login(self, usuario_id: int) -> None:
        """Actualiza last_login al momento actual."""
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE usuarios SET last_login = NOW() WHERE id = %s",
                    (usuario_id,),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"[UsuariosDB] No se pudo actualizar last_login id={usuario_id}: {e}")
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    def seed_admin_desde_env(self, username: str, password_hash: str) -> None:
        """
        Crea el usuario admin inicial a partir de las variables de entorno
        API_USER y API_PASSWORD_HASH si la tabla esta vacia.
        Permite migrar sin rotura de compatibilidad desde el sistema anterior.
        """
        conn = self.pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM usuarios")
                count = cur.fetchone()[0]
            conn.rollback()

            if count > 0:
                return

            # La hash ya viene de .env en formato bcrypt -- la guardamos directamente
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO usuarios (username, password_hash, rol)
                    VALUES (%s, %s, 'admin')
                    ON CONFLICT (username) DO NOTHING
                    """,
                    (username, password_hash),
                )
            conn.commit()
            logger.info(
                f"[UsuariosDB] Usuario admin '{username}' creado desde .env (semilla inicial)"
            )
        except Exception as e:
            conn.rollback()
            logger.error(f"[UsuariosDB] Error en seed_admin_desde_env: {e}")
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    # ------------------------------------------------------------------
    # Refresh tokens (persistentes en BD)
    # ------------------------------------------------------------------

    def crear_refresh_token(self, usuario_id: int,
                             days: int = 7) -> str | None:
        """Genera un refresh token, lo persiste en BD y devuelve el token."""
        from datetime import timedelta
        token = secrets.token_hex(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO refresh_tokens (usuario_id, token, expires_at)
                    VALUES (%s, %s, %s)
                    """,
                    (usuario_id, token, expires_at),
                )
            conn.commit()
            return token
        except Exception as e:
            conn.rollback()
            logger.error(f"[UsuariosDB] Error creando refresh token para id={usuario_id}: {e}")
            return None
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    def consumir_refresh_token(self, token: str) -> dict | None:
        """
        Valida el token: debe existir, no estar revocado y no haber expirado.
        Si es valido lo marca como revocado y devuelve el usuario asociado
        (sin password_hash).
        Devuelve None si el token es invalido o ya fue usado.
        """
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT rt.id, rt.usuario_id, rt.expires_at, rt.revoked,
                           u.username, u.rol, u.activo
                    FROM refresh_tokens rt
                    JOIN usuarios u ON u.id = rt.usuario_id
                    WHERE rt.token = %s
                    """,
                    (token,),
                )
                row = cur.fetchone()

                if row is None:
                    logger.warning("[UsuariosDB] Refresh token desconocido")
                    conn.rollback()
                    return None

                if row["revoked"]:
                    logger.warning(
                        f"[UsuariosDB] Refresh token ya usado (usuario_id={row['usuario_id']})"
                    )
                    conn.rollback()
                    return None

                if row["expires_at"] < datetime.now(timezone.utc):
                    logger.warning(
                        f"[UsuariosDB] Refresh token expirado (usuario_id={row['usuario_id']})"
                    )
                    conn.rollback()
                    return None

                if not row["activo"]:
                    logger.warning(
                        f"[UsuariosDB] Refresh token de usuario inactivo (usuario_id={row['usuario_id']})"
                    )
                    conn.rollback()
                    return None

                # Marcar como revocado (rotacion de tokens: un uso por token)
                cur.execute(
                    "UPDATE refresh_tokens SET revoked = TRUE WHERE id = %s",
                    (row["id"],),
                )
                conn.commit()
                return {
                    "id":       row["usuario_id"],
                    "username": row["username"],
                    "rol":      row["rol"],
                }
        except Exception as e:
            conn.rollback()
            logger.error(f"[UsuariosDB] Error consumiendo refresh token: {e}")
            return None
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    def revocar_todos_tokens(self, usuario_id: int) -> None:
        """Revoca todos los refresh tokens activos de un usuario (logout global)."""
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE refresh_tokens SET revoked = TRUE WHERE usuario_id = %s AND revoked = FALSE",
                    (usuario_id,),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"[UsuariosDB] Error revocando tokens de id={usuario_id}: {e}")
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)

    def limpiar_tokens_expirados(self) -> int:
        """Borra los tokens expirados o revocados. Llamar periodicamente."""
        conn = self.pool.getconn()
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM refresh_tokens
                    WHERE revoked = TRUE OR expires_at < NOW()
                    """
                )
                deleted = cur.rowcount
            conn.commit()
            if deleted:
                logger.info(f"[UsuariosDB] {deleted} tokens expirados/revocados eliminados")
            return deleted
        except Exception as e:
            conn.rollback()
            logger.error(f"[UsuariosDB] Error limpiando tokens: {e}")
            return 0
        finally:
            conn.autocommit = True
            self.pool.putconn(conn)
