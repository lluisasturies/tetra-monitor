import os
import sys
import pytest
import unittest.mock as mock
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

sys.modules.setdefault("psycopg2",        mock.MagicMock())
sys.modules.setdefault("psycopg2.extras", mock.MagicMock())
sys.modules.setdefault("psycopg2.pool",   mock.MagicMock())

from db.usuarios import UsuariosDB, ROLES  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_cur():
    """Cursor mockeado listo para usarse como context manager."""
    cur = mock.MagicMock()
    return cur


def _make_conn(cur=None):
    """
    Conexion mockeada.
    conn.cursor() y conn.cursor(cursor_factory=...) devuelven
    siempre el mismo cursor para que los tests puedan inspeccionarlo.
    """
    if cur is None:
        cur = _make_cur()
    conn = mock.MagicMock()
    cm = mock.MagicMock()
    cm.__enter__ = mock.MagicMock(return_value=cur)
    cm.__exit__  = mock.MagicMock(return_value=False)
    conn.cursor.return_value = cm
    conn._cur = cur
    return conn


def _make_pool(conn=None):
    """Pool que siempre devuelve la misma conexion (o una nueva si no se pasa)."""
    if conn is None:
        conn = _make_conn()
    pool = mock.MagicMock()
    pool.getconn.return_value = conn
    return pool


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

def test_crear_usuario_llama_insert():
    cur = _make_cur()
    cur.fetchone.return_value = {
        "id": 1, "username": "alice", "email": None,
        "rol": "viewer", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    db.crear("alice", "secreto123", rol="viewer")
    assert cur.execute.called
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO usuarios" in sql


def test_crear_usuario_rol_invalido_devuelve_none():
    db = UsuariosDB(_make_pool())
    result = db.crear("bob", "secreto123", rol="superadmin")
    assert result is None


def test_crear_usuario_hashea_contrasena():
    import bcrypt
    cur = _make_cur()
    cur.fetchone.return_value = {
        "id": 2, "username": "carol", "email": None,
        "rol": "admin", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    db.crear("carol", "mipassword", rol="admin")
    call_args = cur.execute.call_args[0][1]
    pw_hash = call_args[2]  # (username, email, password_hash, rol)
    assert bcrypt.checkpw(b"mipassword", pw_hash.encode())


def test_crear_usuario_excepcion_devuelve_none():
    cur = _make_cur()
    cur.execute.side_effect = Exception("duplicate key")
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.crear("dave", "secreto123")
    assert result is None


# ---------------------------------------------------------------------------
# obtener_por_username()
# ---------------------------------------------------------------------------

def test_obtener_por_username_existente():
    cur = _make_cur()
    cur.fetchone.return_value = {
        "id": 1, "username": "alice", "password_hash": "$2b$...",
        "rol": "admin", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.obtener_por_username("alice")
    assert result is not None
    assert result["username"] == "alice"


def test_obtener_por_username_no_existente():
    cur = _make_cur()
    cur.fetchone.return_value = None
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.obtener_por_username("nadie")
    assert result is None


# ---------------------------------------------------------------------------
# listar()
# ---------------------------------------------------------------------------

def test_listar_devuelve_lista():
    cur = _make_cur()
    cur.fetchall.return_value = [
        {"id": 1, "username": "alice", "rol": "admin",    "activo": True,
         "email": None, "created_at": datetime.now(timezone.utc), "last_login": None},
        {"id": 2, "username": "bob",   "rol": "operator", "activo": True,
         "email": None, "created_at": datetime.now(timezone.utc), "last_login": None},
    ]
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.listar()
    assert len(result) == 2
    assert result[0]["username"] == "alice"


def test_listar_excepcion_devuelve_lista_vacia():
    cur = _make_cur()
    cur.fetchall.side_effect = Exception("BD caida")
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.listar()
    assert result == []


# ---------------------------------------------------------------------------
# actualizar()
# ---------------------------------------------------------------------------

def test_actualizar_campos_validos():
    cur = _make_cur()
    cur.fetchone.return_value = {
        "id": 1, "username": "alice", "email": "new@test.com",
        "rol": "operator", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.actualizar(1, email="new@test.com", rol="operator")
    assert result is not None
    assert "UPDATE usuarios" in cur.execute.call_args[0][0]


def test_actualizar_rol_invalido_devuelve_none():
    db = UsuariosDB(_make_pool())
    result = db.actualizar(1, rol="superadmin")
    assert result is None


def test_actualizar_sin_campos_llama_obtener():
    db = UsuariosDB(_make_pool())
    with mock.patch.object(db, "obtener_por_id", return_value={"id": 1}) as mock_obtener:
        db.actualizar(1)
        mock_obtener.assert_called_once_with(1)


def test_actualizar_password_se_hashea():
    import bcrypt
    cur = _make_cur()
    cur.fetchone.return_value = {
        "id": 1, "username": "alice", "email": None,
        "rol": "viewer", "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
    }
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    db.actualizar(1, password="nuevapass")
    sql, params = cur.execute.call_args[0]
    assert "password_hash" in sql
    pw_hash = params[0]  # unico campo actualizado
    assert bcrypt.checkpw(b"nuevapass", pw_hash.encode())


# ---------------------------------------------------------------------------
# seed_admin_desde_env()
# ---------------------------------------------------------------------------

def test_seed_admin_no_inserta_si_hay_usuarios():
    cur = _make_cur()
    cur.fetchone.return_value = (3,)  # 3 usuarios existentes
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    db.seed_admin_desde_env("admin", "$2b$12$hash")
    insert_calls = [c for c in cur.execute.call_args_list if "INSERT" in str(c)]
    assert len(insert_calls) == 0


def test_seed_admin_inserta_si_tabla_vacia():
    """
    seed_admin_desde_env usa UNA sola conexion para el COUNT y el INSERT.
    fetchone devuelve (0,) la primera llamada (COUNT=0) y None las siguientes.
    Verificamos que el INSERT se ejecuto sobre el mismo cursor.
    """
    cur = _make_cur()
    cur.fetchone.return_value = (0,)  # tabla vacia
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    db.seed_admin_desde_env("admin", "$2b$12$hash")
    insert_calls = [c for c in cur.execute.call_args_list if "INSERT" in str(c)]
    assert len(insert_calls) == 1


# ---------------------------------------------------------------------------
# crear_refresh_token()
# ---------------------------------------------------------------------------

def test_crear_refresh_token_devuelve_string():
    db = UsuariosDB(_make_pool())
    token = db.crear_refresh_token(usuario_id=1)
    assert isinstance(token, str)
    assert len(token) == 64  # secrets.token_hex(32)


def test_crear_refresh_token_inserta_en_bd():
    cur = _make_cur()
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    db.crear_refresh_token(usuario_id=1)
    sql = cur.execute.call_args[0][0]
    assert "INSERT INTO refresh_tokens" in sql


def test_crear_refresh_token_excepcion_devuelve_none():
    cur = _make_cur()
    cur.execute.side_effect = Exception("BD caida")
    db = UsuariosDB(_make_pool(_make_conn(cur)))
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


def test_consumir_token_valido_devuelve_usuario():
    cur = _make_cur()
    cur.fetchone.return_value = _token_row()
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.consumir_refresh_token("token_valido")
    assert result is not None
    assert result["username"] == "alice"
    assert result["rol"] == "admin"


def test_consumir_token_valido_marca_revocado():
    cur = _make_cur()
    cur.fetchone.return_value = _token_row()
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    db.consumir_refresh_token("token_valido")
    update_calls = [
        c for c in cur.execute.call_args_list
        if "revoked = TRUE" in str(c) and "refresh_tokens" in str(c)
    ]
    assert len(update_calls) == 1


def test_consumir_token_desconocido_devuelve_none():
    cur = _make_cur()
    cur.fetchone.return_value = None
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.consumir_refresh_token("token_falso")
    assert result is None


def test_consumir_token_ya_revocado_devuelve_none():
    cur = _make_cur()
    cur.fetchone.return_value = _token_row(revoked=True)
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.consumir_refresh_token("token_revocado")
    assert result is None


def test_consumir_token_expirado_devuelve_none():
    cur = _make_cur()
    cur.fetchone.return_value = _token_row(expired=True)
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.consumir_refresh_token("token_expirado")
    assert result is None


def test_consumir_token_usuario_inactivo_devuelve_none():
    cur = _make_cur()
    cur.fetchone.return_value = _token_row(activo=False)
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    result = db.consumir_refresh_token("token_inactivo")
    assert result is None


# ---------------------------------------------------------------------------
# revocar_todos_tokens()
# ---------------------------------------------------------------------------

def test_revocar_todos_tokens_ejecuta_update():
    cur = _make_cur()
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    db.revocar_todos_tokens(usuario_id=1)
    sql = cur.execute.call_args[0][0]
    assert "UPDATE refresh_tokens" in sql
    assert "revoked = TRUE" in sql


# ---------------------------------------------------------------------------
# limpiar_tokens_expirados()
# ---------------------------------------------------------------------------

def test_limpiar_tokens_expirados_ejecuta_delete():
    cur = _make_cur()
    cur.rowcount = 5
    db = UsuariosDB(_make_pool(_make_conn(cur)))
    deleted = db.limpiar_tokens_expirados()
    assert deleted == 5
    sql = cur.execute.call_args[0][0]
    assert "DELETE FROM refresh_tokens" in sql
