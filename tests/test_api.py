import os
import sys
import pytest
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Mocks de dependencias de hardware antes de importar la app
sys.modules.setdefault("serial", mock.MagicMock())
sys.modules.setdefault("sounddevice", mock.MagicMock())
sys.modules.setdefault("soundfile", mock.MagicMock())
sys.modules.setdefault("whisper", mock.MagicMock())

from fastapi.testclient import TestClient  # noqa: E402
from app_state import app_state  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_app_state():
    """Limpia app_state entre tests para evitar contaminación."""
    app_state.pool             = None
    app_state.llamadas         = None
    app_state.grupos           = None
    app_state.afiliacion       = None
    app_state.bot              = None
    app_state.radio_connected  = False
    app_state.streaming_active = False
    app_state.refresh_tokens   = set()
    yield
    app_state.refresh_tokens   = set()


@pytest.fixture
def client(monkeypatch):
    """Cliente de test con variables de entorno mínimas y app_state mockeado."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-suficientemente-larga")
    monkeypatch.setenv("API_USER", "admin")
    # Hash bcrypt de "testpass"
    monkeypatch.setenv("API_PASSWORD_HASH", "$2b$12$KIXsP3OVzvBKMtSdW9na5.kX4nFn2KsGBPDwZ6HUMVf7yXlV/uyTa")

    # Evitar que _init_standalone intente conectar a BD real
    monkeypatch.setattr("api.api._init_standalone", lambda: None)

    from api.api import app
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_degraded_sin_subsistemas(client):
    """Sin BD ni PEI inicializados: status degraded y HTTP 503."""
    resp = client.get("/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["db"] is False
    assert data["pei"] is False
    assert data["radio"] is False
    assert data["streaming"] is False


def test_health_ok_con_subsistemas_activos(client):
    """Con BD, PEI y radio mockeados: status ok y HTTP 200."""
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
    """Con BD y PEI activos pero radio desconectada: status degraded y HTTP 503."""
    app_state.pool       = mock.MagicMock()
    app_state.afiliacion = mock.MagicMock()
    # radio_connected = False (por defecto del fixture)
    resp = client.get("/health")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["radio"] is False


def test_health_streaming_activo(client):
    """El campo streaming refleja app_state.streaming_active."""
    app_state.pool             = mock.MagicMock()
    app_state.afiliacion       = mock.MagicMock()
    app_state.radio_connected  = True
    app_state.streaming_active = True
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["streaming"] is True
    assert data["status"] == "ok"  # streaming no afecta a status


# ---------------------------------------------------------------------------
# /auth/token
# ---------------------------------------------------------------------------

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
# /calls — con BD mockeada
# ---------------------------------------------------------------------------

def test_calls_servicio_no_disponible(client, monkeypatch):
    """Sin BD inicializada debe devolver 503."""
    import bcrypt
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    monkeypatch.setenv("API_PASSWORD_HASH", hashed)

    import importlib
    import api.api as api_module
    importlib.reload(api_module)
    monkeypatch.setattr("api.api._init_standalone", lambda: None)

    from fastapi.testclient import TestClient
    c = TestClient(api_module.app)
    token_resp = c.post("/auth/token", data={"username": "admin", "password": "testpass"})
    token = token_resp.json()["access_token"]

    resp = c.get("/calls", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 503


def test_calls_con_bd_mockeada(client, monkeypatch):
    """Con BD mockeada debe devolver resultados correctamente."""
    import bcrypt
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    monkeypatch.setenv("API_PASSWORD_HASH", hashed)

    import importlib
    import api.api as api_module
    importlib.reload(api_module)
    monkeypatch.setattr("api.api._init_standalone", lambda: None)

    from fastapi.testclient import TestClient
    c = TestClient(api_module.app)
    token = c.post("/auth/token", data={"username": "admin", "password": "testpass"}).json()["access_token"]

    llamadas_mock = mock.MagicMock()
    llamadas_mock.listar_filtrado.return_value = ([], 0)
    app_state.llamadas = llamadas_mock

    resp = c.get("/calls", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["results"] == []


# ---------------------------------------------------------------------------
# /afiliacion — con afiliacion mockeada
# ---------------------------------------------------------------------------

def test_afiliacion_con_estado_mockeado(client, monkeypatch):
    import bcrypt
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    monkeypatch.setenv("API_PASSWORD_HASH", hashed)

    import importlib
    import api.api as api_module
    importlib.reload(api_module)
    monkeypatch.setattr("api.api._init_standalone", lambda: None)

    from fastapi.testclient import TestClient
    c = TestClient(api_module.app)
    token = c.post("/auth/token", data={"username": "admin", "password": "testpass"}).json()["access_token"]

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
    resp = client.post("/auth/refresh", json={"refresh_token": "token-falso"})
    assert resp.status_code == 401


def test_logout_token_invalido_no_falla(client):
    """Logout con token inválido debe devolver 200 (idempotente)."""
    resp = client.post("/auth/logout", json={"refresh_token": "token-inexistente"})
    assert resp.status_code == 200
