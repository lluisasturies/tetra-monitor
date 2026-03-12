import os
import sys
import pytest
import unittest.mock as mock
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Mocks de dependencias de hardware antes de importar la app
sys.modules.setdefault("serial",      mock.MagicMock())
sys.modules.setdefault("sounddevice", mock.MagicMock())
sys.modules.setdefault("soundfile",   mock.MagicMock())
sys.modules.setdefault("whisper",     mock.MagicMock())

from fastapi.testclient import TestClient  # noqa: E402
from app_state import app_state            # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_usuarios_mock(username="admin", password="testpass", rol="admin"):
    """
    Devuelve un mock de UsuariosDB que autentica al usuario indicado.
    crear_refresh_token devuelve un token fijo para facilitar los tests.
    consumir_refresh_token devuelve None (token invalido por defecto).
    """
    import bcrypt
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    usuario = {
        "id": 1, "username": username, "email": None,
        "rol": rol, "activo": True,
        "created_at": datetime.now(timezone.utc), "last_login": None,
        "password_hash": pw_hash,
    }
    m = mock.MagicMock()
    m.obtener_por_username.side_effect = (
        lambda u: usuario if u == username else None
    )
    m.obtener_por_id.return_value = {k: v for k, v in usuario.items() if k != "password_hash"}
    m.crear_refresh_token.return_value = "refresh-token-fijo"
    m.consumir_refresh_token.return_value = None
    return m


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_app_state():
    """Limpia app_state entre tests para evitar contaminacion."""
    app_state.pool             = None
    app_state.llamadas         = None
    app_state.grupos           = None
    app_state.usuarios         = None
    app_state.afiliacion       = None
    app_state.bot              = None
    app_state.radio_connected  = False
    app_state.streaming_active = False
    app_state.refresh_tokens   = set()
    yield
    app_state.refresh_tokens   = set()


@pytest.fixture
def client(monkeypatch):
    """Cliente de test con app_state.usuarios mockeado."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-suficientemente-larga")
    monkeypatch.setenv("API_USER", "admin")
    monkeypatch.setenv("API_PASSWORD_HASH", "$2b$12$dummy")
    monkeypatch.setattr("api.api._init_standalone", lambda: None)

    from api.api import app
    app_state.usuarios = _make_usuarios_mock()
    return TestClient(app, raise_server_exceptions=True)


def _client_with_token(monkeypatch, password="testpass"):
    """Devuelve (TestClient, token) con usuarios mockeado y login correcto."""
    import importlib
    import api.api as api_module

    monkeypatch.setenv("JWT_SECRET", "test-secret-key-suficientemente-larga")
    monkeypatch.setenv("API_USER", "admin")
    monkeypatch.setenv("API_PASSWORD_HASH", "$2b$12$dummy")
    monkeypatch.setattr("api.api._init_standalone", lambda: None)

    importlib.reload(api_module)
    app_state.usuarios = _make_usuarios_mock(password=password)

    c = TestClient(api_module.app, raise_server_exceptions=True)
    token = c.post("/auth/token", data={"username": "admin", "password": password}).json()["access_token"]
    return c, token


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_degraded_sin_subsistemas(client):
    resp = client.get("/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["db"] is False
    assert data["pei"] is False
    assert data["radio"] is False
    assert data["streaming"] is False


def test_health_ok_con_subsistemas_activos(client):
    app_state.pool            = mock.MagicMock()
    app_state.afiliacion      = mock.MagicMock()
    app_state.radio_connected = True
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["db"] is True
    assert data["pei"] is True
    assert data["radio"] is True


def test_health_degraded_si_radio_desconectada(client):
    app_state.pool       = mock.MagicMock()
    app_state.afiliacion = mock.MagicMock()
    resp = client.get("/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["radio"] is False


def test_health_streaming_activo(client):
    app_state.pool             = mock.MagicMock()
    app_state.afiliacion       = mock.MagicMock()
    app_state.radio_connected  = True
    app_state.streaming_active = True
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["streaming"] is True


# ---------------------------------------------------------------------------
# /auth/token
# ---------------------------------------------------------------------------

def test_login_correcto(client):
    resp = client.post("/auth/token", data={"username": "admin", "password": "testpass"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_credenciales_incorrectas(client):
    resp = client.post("/auth/token", data={"username": "admin", "password": "wrongpass"})
    assert resp.status_code == 401


def test_login_usuario_incorrecto(client):
    resp = client.post("/auth/token", data={"username": "hacker", "password": "testpass"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Endpoints protegidos sin token
# ---------------------------------------------------------------------------

def test_calls_sin_token(client):
    resp = client.get("/calls")
    assert resp.status_code == 401


def test_afiliacion_sin_token(client):
    resp = client.get("/afiliacion")
    assert resp.status_code == 401


def test_groups_sin_token(client):
    resp = client.get("/groups")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /calls
# ---------------------------------------------------------------------------

def test_calls_servicio_no_disponible(monkeypatch):
    """Con BD (llamadas) a None debe devolver 503."""
    c, token = _client_with_token(monkeypatch)
    app_state.llamadas = None
    resp = c.get("/calls", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 503


def test_calls_con_bd_mockeada(monkeypatch):
    c, token = _client_with_token(monkeypatch)
    llamadas_mock = mock.MagicMock()
    llamadas_mock.listar_filtrado.return_value = ([], 0)
    app_state.llamadas = llamadas_mock
    resp = c.get("/calls", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["results"] == []


# ---------------------------------------------------------------------------
# /afiliacion
# ---------------------------------------------------------------------------

def test_afiliacion_con_estado_mockeado(monkeypatch):
    c, token = _client_with_token(monkeypatch)
    afiliacion_mock = mock.MagicMock()
    afiliacion_mock.gssi = "36001"
    afiliacion_mock.scan_list = "ListaScan1"
    app_state.afiliacion = afiliacion_mock
    resp = c.get("/afiliacion", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["gssi"] == "36001"
    assert data["scan_list"] == "ListaScan1"


# ---------------------------------------------------------------------------
# /auth/refresh y /auth/logout
# ---------------------------------------------------------------------------

def test_refresh_token_invalido(client):
    # consumir_refresh_token devuelve None por defecto en el mock
    resp = client.post("/auth/refresh", json={"refresh_token": "token-falso"})
    assert resp.status_code == 401


def test_logout_con_token_valido(client):
    token_resp = client.post("/auth/token", data={"username": "admin", "password": "testpass"})
    access = token_resp.json()["access_token"]
    resp = client.post(
        "/auth/logout",
        json={"refresh_token": "token-inexistente"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 200


def test_logout_sin_token_devuelve_401(client):
    resp = client.post("/auth/logout", json={"refresh_token": "token-inexistente"})
    assert resp.status_code == 401
