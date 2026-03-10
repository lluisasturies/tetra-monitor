import os
import sys
import pytest
import yaml
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

sys.modules.setdefault("serial",      mock.MagicMock())
sys.modules.setdefault("sounddevice", mock.MagicMock())
sys.modules.setdefault("soundfile",   mock.MagicMock())
sys.modules.setdefault("whisper",     mock.MagicMock())

from fastapi.testclient import TestClient  # noqa: E402
from app_state import app_state           # noqa: E402
from filters.keyword_filter import KeywordFilter  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def keywords_file(tmp_path):
    path = tmp_path / "keywords.yaml"
    path.write_text(yaml.dump({"keywords": ["incendio", "falla cámara"]}))
    return path


@pytest.fixture(autouse=True)
def reset_app_state():
    app_state.pool             = None
    app_state.llamadas         = None
    app_state.grupos           = None
    app_state.afiliacion       = None
    app_state.bot              = None
    app_state.keyword_filter   = None
    app_state.radio_connected  = False
    app_state.streaming_active = False
    app_state.refresh_tokens   = set()
    yield
    app_state.refresh_tokens   = set()


@pytest.fixture
def client(monkeypatch, keywords_file):
    monkeypatch.setenv("JWT_SECRET", "test-secret-key-suficientemente-larga")
    monkeypatch.setenv("API_USER", "admin")
    monkeypatch.setenv("API_PASSWORD_HASH", "$2b$12$KIXsP3OVzvBKMtSdW9na5.kX4nFn2KsGBPDwZ6HUMVf7yXlV/uyTa")
    monkeypatch.setattr("api.api._init_standalone", lambda: None)

    app_state.keyword_filter = KeywordFilter(str(keywords_file))

    from api.api import app
    return TestClient(app, raise_server_exceptions=True)


def _get_token(client):
    import bcrypt, importlib, api.api as api_module
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    import os; os.environ["API_PASSWORD_HASH"] = hashed
    importlib.reload(api_module)
    c = TestClient(api_module.app)
    return c.post("/auth/token", data={"username": "admin", "password": "testpass"}).json()["access_token"], c


# ---------------------------------------------------------------------------
# KeywordFilter unitario
# ---------------------------------------------------------------------------

def test_add_nueva_keyword(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    added = kf.add("explosión")
    assert added is True
    assert "explosión" in kf.keywords


def test_add_keyword_duplicada(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    added = kf.add("incendio")
    assert added is False
    assert kf.keywords.count("incendio") == 1


def test_add_normaliza_a_minusculas(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    kf.add("EXPLOSIÓN")
    assert "explosión" in kf.keywords
    assert "EXPLOSIÓN" not in kf.keywords


def test_add_persiste_en_disco(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    kf.add("nuevo evento")
    with open(keywords_file) as f:
        data = yaml.safe_load(f)
    assert "nuevo evento" in data["keywords"]


def test_remove_keyword_existente(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    removed = kf.remove("incendio")
    assert removed is True
    assert "incendio" not in kf.keywords


def test_remove_keyword_inexistente(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    removed = kf.remove("no existe")
    assert removed is False


def test_remove_persiste_en_disco(keywords_file):
    kf = KeywordFilter(str(keywords_file))
    kf.remove("incendio")
    with open(keywords_file) as f:
        data = yaml.safe_load(f)
    assert "incendio" not in data["keywords"]


def test_save_unicode(keywords_file):
    """Las keywords con tildes y caracteres especiales se guardan correctamente."""
    kf = KeywordFilter(str(keywords_file))
    kf.add("inundación")
    kf2 = KeywordFilter(str(keywords_file))
    assert "inundación" in kf2.keywords


# ---------------------------------------------------------------------------
# API /keywords
# ---------------------------------------------------------------------------

def test_keywords_sin_token(client):
    resp = client.get("/keywords")
    assert resp.status_code == 401


def test_get_keywords(monkeypatch, keywords_file):
    token, c = _get_token(TestClient.__new__(TestClient))
    monkeypatch.setattr("api.api._init_standalone", lambda: None)
    import importlib, api.api as api_module
    importlib.reload(api_module)
    c2 = TestClient(api_module.app)
    import bcrypt, os
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    os.environ["API_PASSWORD_HASH"] = hashed
    importlib.reload(api_module)
    c2 = TestClient(api_module.app)
    token = c2.post("/auth/token", data={"username": "admin", "password": "testpass"}).json()["access_token"]
    app_state.keyword_filter = KeywordFilter(str(keywords_file))
    resp = c2.get("/keywords", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "incendio" in resp.json()["keywords"]


def test_post_keyword_nueva(monkeypatch, keywords_file):
    import bcrypt, importlib, api.api as api_module, os
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    os.environ["API_PASSWORD_HASH"] = hashed
    monkeypatch.setattr("api.api._init_standalone", lambda: None)
    importlib.reload(api_module)
    c = TestClient(api_module.app)
    token = c.post("/auth/token", data={"username": "admin", "password": "testpass"}).json()["access_token"]
    app_state.keyword_filter = KeywordFilter(str(keywords_file))
    resp = c.post("/keywords", json={"keyword": "explosión"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "explosión" in resp.json()["keywords"]


def test_post_keyword_duplicada_devuelve_409(monkeypatch, keywords_file):
    import bcrypt, importlib, api.api as api_module, os
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    os.environ["API_PASSWORD_HASH"] = hashed
    monkeypatch.setattr("api.api._init_standalone", lambda: None)
    importlib.reload(api_module)
    c = TestClient(api_module.app)
    token = c.post("/auth/token", data={"username": "admin", "password": "testpass"}).json()["access_token"]
    app_state.keyword_filter = KeywordFilter(str(keywords_file))
    resp = c.post("/keywords", json={"keyword": "incendio"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 409


def test_delete_keyword_existente(monkeypatch, keywords_file):
    import bcrypt, importlib, api.api as api_module, os
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    os.environ["API_PASSWORD_HASH"] = hashed
    monkeypatch.setattr("api.api._init_standalone", lambda: None)
    importlib.reload(api_module)
    c = TestClient(api_module.app)
    token = c.post("/auth/token", data={"username": "admin", "password": "testpass"}).json()["access_token"]
    app_state.keyword_filter = KeywordFilter(str(keywords_file))
    resp = c.delete("/keywords/incendio", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "incendio" not in resp.json()["keywords"]


def test_delete_keyword_inexistente_devuelve_404(monkeypatch, keywords_file):
    import bcrypt, importlib, api.api as api_module, os
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    os.environ["API_PASSWORD_HASH"] = hashed
    monkeypatch.setattr("api.api._init_standalone", lambda: None)
    importlib.reload(api_module)
    c = TestClient(api_module.app)
    token = c.post("/auth/token", data={"username": "admin", "password": "testpass"}).json()["access_token"]
    app_state.keyword_filter = KeywordFilter(str(keywords_file))
    resp = c.delete("/keywords/no-existe", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


def test_keywords_sin_filtro_devuelve_503(monkeypatch):
    import bcrypt, importlib, api.api as api_module, os
    hashed = bcrypt.hashpw(b"testpass", bcrypt.gensalt()).decode()
    os.environ["API_PASSWORD_HASH"] = hashed
    monkeypatch.setattr("api.api._init_standalone", lambda: None)
    importlib.reload(api_module)
    c = TestClient(api_module.app)
    token = c.post("/auth/token", data={"username": "admin", "password": "testpass"}).json()["access_token"]
    app_state.keyword_filter = None  # sin filtro
    resp = c.get("/keywords", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 503
