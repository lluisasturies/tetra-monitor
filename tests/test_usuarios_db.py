import os
import sys
import time
import pytest
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

sys.modules.setdefault("psycopg2",          mock.MagicMock())
sys.modules.setdefault("psycopg2.extras",   mock.MagicMock())
sys.modules.setdefault("psycopg2.pool",     mock.MagicMock())

from db.usuarios import UsuariosDB, ROLES  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool():
    """Pool mockeado que devuelve una conexion fresh en cada getconn()."""
    pool = mock.MagicMock()
    pool.getconn.side_effect = lambda: _make_conn()
    return pool


def _make_conn():
    conn = mock.MagicMock()
    cur  = mock.MagicMock()
    conn.cursor.return_value.__enter__ = lambda s: cur
    conn.cursor.return_value.__exit__  = mock.MagicMock(return_value=False)
    conn._cur = cur
    return conn


@pytest.fixture
def db():
    return UsuariosDB(_make_pool())


# ---------------------------------------------------------------------------
# ROLES
# ---------------------------------------------------------------------------

def test_roles_orden_correcto():
    assert ROLES == ("viewer", "operator", "admin")


def test_roles_contiene_tres_valores():
    assert len(ROLES) == 3


# ---------------------------------------------------------------------------
# crear()
# ---------------------------------------------------------------------------

def test_crear_usuario_llama_insert(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    cur = conn._cur
    cur.fetchone.return_value = {
        "id": 1, "username": "alice", "email": None,
        "rol": "viewer", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    from psycopg2.extras import RealDictCursor
    conn.cursor.return_value.__enter__ = lambda s: cur
    result = db.crear("alice", "secreto123", rol="viewer")
    assert cur.execute.called
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO usuarios" in sql


def test_crear_usuario_rol_invalido_devuelve_none(db):
    result = db.crear("bob", "secreto123", rol="superadmin")
    assert result is None


def test_crear_usuario_hashea_contrasena(db):
    import bcrypt
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    cur = conn._cur
    cur.fetchone.return_value = {
        "id": 2, "username": "carol", "email": None,
        "rol": "admin", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    db.crear("carol", "mipassword", rol="admin")
    # El segundo arg del INSERT es el hash bcrypt
    call_args = cur.execute.call_args[0][1]
    pw_hash = call_args[2]  # (username, email, password_hash, rol)
    assert bcrypt.checkpw(b"mipassword", pw_hash.encode())


def test_crear_usuario_excepcion_devuelve_none(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn.cursor.return_value.__enter__ = mock.MagicMock(
        side_effect=Exception("duplicate key")
    )
    result = db.crear("dave", "secreto123")
    assert result is None


# ---------------------------------------------------------------------------
# obtener_por_username()
# ---------------------------------------------------------------------------

def test_obtener_por_username_existente(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    cur = conn._cur
    cur.fetchone.return_value = {
        "id": 1, "username": "alice", "password_hash": "$2b$...",
        "rol": "admin", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    result = db.obtener_por_username("alice")
    assert result is not None
    assert result["username"] == "alice"


def test_obtener_por_username_no_existente(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchone.return_value = None
    result = db.obtener_por_username("nadie")
    assert result is None


# ---------------------------------------------------------------------------
# listar()
# ---------------------------------------------------------------------------

def test_listar_devuelve_lista(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchall.return_value = [
        {"id": 1, "username": "alice", "rol": "admin",    "activo": True,
         "email": None, "created_at": datetime.now(timezone.utc), "last_login": None},
        {"id": 2, "username": "bob",   "rol": "operator", "activo": True,
         "email": None, "created_at": datetime.now(timezone.utc), "last_login": None},
    ]
    result = db.listar()
    assert len(result) == 2
    assert result[0]["username"] == "alice"


def test_listar_excepcion_devuelve_lista_vacia(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchall.side_effect = Exception("BD caida")
    result = db.listar()
    assert result == []


# ---------------------------------------------------------------------------
# actualizar()
# ---------------------------------------------------------------------------

def test_actualizar_campos_validos(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    cur = conn._cur
    cur.fetchone.return_value = {
        "id": 1, "username": "alice", "email": "new@test.com",
        "rol": "operator", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    result = db.actualizar(1, email="new@test.com", rol="operator")
    assert result is not None
    assert "UPDATE usuarios" in cur.execute.call_args[0][0]


def test_actualizar_rol_invalido_devuelve_none(db):
    result = db.actualizar(1, rol="superadmin")
    assert result is None


def test_actualizar_sin_campos_llama_obtener(db):
    with mock.patch.object(db, "obtener_por_id", return_value={"id": 1}) as mock_obtener:
        result = db.actualizar(1)
        mock_obtener.assert_called_once_with(1)


def test_actualizar_password_se_hashea(db):
    import bcrypt
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    cur = conn._cur
    cur.fetchone.return_value = {
        "id": 1, "username": "alice", "email": None,
        "rol": "viewer", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    db.actualizar(1, password="nuevapass")
    sql, params = cur.execute.call_args[0]
    assert "password_hash" in sql
    pw_hash = params[0]  # unico campo actualizado
    assert bcrypt.checkpw(b"nuevapass", pw_hash.encode())


# ---------------------------------------------------------------------------
# seed_admin_desde_env()
# ---------------------------------------------------------------------------

def test_seed_admin_no_inserta_si_hay_usuarios(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchone.return_value = (3,)  # 3 usuarios existentes
    db.seed_admin_desde_env("admin", "$2b$12$hash")
    # El INSERT no debe haberse ejecutado
    insert_calls = [
        c for c in conn._cur.execute.call_args_list
        if "INSERT" in str(c)
    ]
    assert len(insert_calls) == 0


def test_seed_admin_inserta_si_tabla_vacia(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchone.return_value = (0,)  # tabla vacia
    db.seed_admin_desde_env("admin", "$2b$12$hash")
    insert_calls = [
        c for c in conn._cur.execute.call_args_list
        if "INSERT" in str(c)
    ]
    assert len(insert_calls) == 1


# ---------------------------------------------------------------------------
# crear_refresh_token()
# ---------------------------------------------------------------------------

def test_crear_refresh_token_devuelve_string(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    token = db.crear_refresh_token(usuario_id=1)
    assert isinstance(token, str)
    assert len(token) == 64  # secrets.token_hex(32)


def test_crear_refresh_token_inserta_en_bd(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    db.crear_refresh_token(usuario_id=1)
    sql = conn._cur.execute.call_args[0][0]
    assert "INSERT INTO refresh_tokens" in sql


def test_crear_refresh_token_excepcion_devuelve_none(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.execute.side_effect = Exception("BD caida")
    result = db.crear_refresh_token(usuario_id=1)
    assert result is None


# ---------------------------------------------------------------------------
# consumir_refresh_token()
# ---------------------------------------------------------------------------

def _token_row(revoked=False, expired=False, activo=True):
    now = datetime.now(timezone.utc)
    return {
        "id": 10,
        "usuario_id": 1,
        "expires_at": now - timedelta(hours=1) if expired else now + timedelta(days=7),
        "revoked": revoked,
        "username": "alice",
        "rol": "admin",
        "activo": activo,
    }


def test_consumir_token_valido_devuelve_usuario(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchone.return_value = _token_row()
    result = db.consumir_refresh_token("token_valido")
    assert result is not None
    assert result["username"] == "alice"
    assert result["rol"] == "admin"


def test_consumir_token_valido_marca_revocado(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchone.return_value = _token_row()
    db.consumir_refresh_token("token_valido")
    update_calls = [
        c for c in conn._cur.execute.call_args_list
        if "revoked = TRUE" in str(c) and "refresh_tokens" in str(c)
    ]
    assert len(update_calls) == 1


def test_consumir_token_desconocido_devuelve_none(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchone.return_value = None
    result = db.consumir_refresh_token("token_falso")
    assert result is None


def test_consumir_token_ya_revocado_devuelve_none(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchone.return_value = _token_row(revoked=True)
    result = db.consumir_refresh_token("token_revocado")
    assert result is None


def test_consumir_token_expirado_devuelve_none(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchone.return_value = _token_row(expired=True)
    result = db.consumir_refresh_token("token_expirado")
    assert result is None


def test_consumir_token_usuario_inactivo_devuelve_none(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.fetchone.return_value = _token_row(activo=False)
    result = db.consumir_refresh_token("token_inactivo")
    assert result is None


# ---------------------------------------------------------------------------
# revocar_todos_tokens()
# ---------------------------------------------------------------------------

def test_revocar_todos_tokens_ejecuta_update(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    db.revocar_todos_tokens(usuario_id=1)
    sql = conn._cur.execute.call_args[0][0]
    assert "UPDATE refresh_tokens" in sql
    assert "revoked = TRUE" in sql


# ---------------------------------------------------------------------------
# limpiar_tokens_expirados()
# ---------------------------------------------------------------------------

def test_limpiar_tokens_expirados_ejecuta_delete(db):
    conn = _make_conn()
    db.pool.getconn.return_value = conn
    conn._cur.rowcount = 5
    deleted = db.limpiar_tokens_expirados()
    assert deleted == 5
    sql = conn._cur.execute.call_args[0][0]
    assert "DELETE FROM refresh_tokens" in sql
