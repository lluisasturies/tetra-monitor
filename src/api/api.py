import os
import secrets
import bcrypt
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from jose import JWTError, jwt
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

from core.logger import logger
from app_state import app_state

JWT_SECRET        = os.getenv("JWT_SECRET")
API_USER          = os.getenv("API_USER")
API_PASSWORD_HASH = os.getenv("API_PASSWORD_HASH", "").encode()

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET no definido en .env")
if not API_USER or not API_PASSWORD_HASH:
    raise RuntimeError("API_USER y API_PASSWORD_HASH deben estar definidos en .env")

JWT_ALGORITHM      = "HS256"
ACCESS_TOKEN_HOURS = 1
REFRESH_TOKEN_DAYS = 7

_cors_env = os.getenv("CORS_ORIGINS", "")
CORS_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] or ["http://localhost"]


# ------------------------------------------------------------------
# Startup autónomo — solo actúa si main.py no ha inicializado el estado
# ------------------------------------------------------------------

def _init_standalone():
    """
    Inicializa el pool, repositorios y afiliacion config cuando la API
    arranca de forma independiente (desarrollo / testing sin main.py).
    Si app_state ya está inicializado (arrancado desde main.py), no hace nada.
    """
    if app_state.pool is not None:
        return  # ya inicializado por main.py

    import yaml
    from pathlib import Path
    from db.pool import DBPool
    from db.llamadas import LlamadasDB
    from db.grupos import GruposDB
    from core.afiliacion import AfiliacionConfig

    logger.info("[API standalone] Inicializando dependencias sin main.py...")

    PROJECT_ROOT    = Path(__file__).resolve().parents[2]
    CONFIG_PATH     = PROJECT_ROOT / "config" / "config.yaml"
    AFILIACION_PATH = PROJECT_ROOT / "config" / "afiliacion.yaml"
    GRUPOS_PATH     = PROJECT_ROOT / "config" / "grupos.yaml"

    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"[API standalone] No se pudo leer config.yaml: {e}")
        return

    db_user     = os.getenv("DB_USER", "")
    db_password = os.getenv("DB_PASSWORD", "")

    try:
        pool = DBPool(
            host=cfg["database"]["host"],
            port=cfg["database"]["port"],
            dbname=cfg["database"]["dbname"],
            user=db_user,
            password=db_password,
        )
    except Exception as e:
        logger.error(f"[API standalone] No se pudo conectar a la BD: {e}")
        return

    llamadas_db = LlamadasDB(pool)
    grupos_db   = GruposDB(pool)
    afiliacion  = AfiliacionConfig(AFILIACION_PATH)

    app_state.pool      = pool
    app_state.llamadas  = llamadas_db
    app_state.grupos    = grupos_db
    app_state.afiliacion = afiliacion

    grupos_db.seed_from_yaml(GRUPOS_PATH)
    logger.info("[API standalone] Dependencias inicializadas correctamente")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_standalone()
    yield


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="TETRA Monitor API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _safe_username(username: str) -> str:
    cleaned = username[:32]
    return cleaned if len(username) <= 32 else cleaned + "…"

def _require_llamadas():
    if app_state.llamadas is None:
        raise HTTPException(status_code=503, detail="Servicio no disponible aún")

def _require_afiliacion():
    if app_state.afiliacion is None:
        raise HTTPException(status_code=503, detail="Servicio no disponible aún")

def _require_grupos():
    if app_state.grupos is None:
        raise HTTPException(status_code=503, detail="Servicio no disponible aún")


# ------------------------------------------------------------------
# JWT
# ------------------------------------------------------------------

def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token() -> str:
    token = secrets.token_hex(32)
    app_state.refresh_tokens.add(token)
    return token


def verify_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = payload.get("sub")
        if not user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user
    except JWTError:
        logger.warning("Intento de acceso con token JWT inválido o expirado")
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


# ------------------------------------------------------------------
# Modelos Pydantic
# ------------------------------------------------------------------

class GSSIUpdate(BaseModel):
    gssi: str

class ScanListUpdate(BaseModel):
    scan_list: str

class RefreshRequest(BaseModel):
    refresh_token: str

class GrupoUpsert(BaseModel):
    gssi: int
    nombre: str
    descripcion: str | None = None
    activo: bool = True


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@app.get("/health")
@limiter.limit("30/minute")
def health(request: Request):
    return {"status": "ok"}


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------

@app.post("/auth/token")
@limiter.limit("5/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    password_ok = bcrypt.checkpw(form_data.password.encode(), API_PASSWORD_HASH)
    if form_data.username != API_USER or not password_ok:
        logger.warning(f"Intento de login fallido para usuario '{_safe_username(form_data.username)}'")
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    access_token  = create_access_token(form_data.username)
    refresh_token = create_refresh_token()
    logger.info(f"Login correcto para '{_safe_username(form_data.username)}'")
    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TOKEN_HOURS * 3600,
    }


@app.post("/auth/refresh")
@limiter.limit("10/minute")
def refresh(request: Request, body: RefreshRequest):
    if body.refresh_token not in app_state.refresh_tokens:
        logger.warning("Intento de refresh con token inválido o ya usado")
        raise HTTPException(status_code=401, detail="Refresh token inválido o expirado")
    app_state.refresh_tokens.discard(body.refresh_token)
    new_refresh  = create_refresh_token()
    access_token = create_access_token(API_USER)
    logger.info("Access token renovado correctamente")
    return {
        "access_token":  access_token,
        "refresh_token": new_refresh,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TOKEN_HOURS * 3600,
    }


@app.post("/auth/logout")
@limiter.limit("10/minute")
def logout(request: Request, body: RefreshRequest):
    app_state.refresh_tokens.discard(body.refresh_token)
    logger.info("Sesión cerrada correctamente")
    return {"status": "ok"}


# ------------------------------------------------------------------
# Llamadas
# ------------------------------------------------------------------

@app.get("/calls", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def listar_llamadas(
    request: Request,
    limit:  int      = Query(default=50,   ge=1, le=500, description="Resultados por página"),
    offset: int      = Query(default=0,    ge=0,         description="Desplazamiento para paginación"),
    gssi:   int|None = Query(default=None,               description="Filtrar por GSSI (grupo)"),
    ssi:    int|None = Query(default=None,               description="Filtrar por SSI (emisor)"),
    texto:  str|None = Query(default=None,               description="Buscar en transcripción (contiene)"),
):
    _require_llamadas()
    rows, total = app_state.llamadas.listar_filtrado(
        limit=limit, offset=offset, gssi=gssi, ssi=ssi, texto=texto
    )
    return {
        "total":   total,
        "limit":   limit,
        "offset":  offset,
        "results": [dict(r) for r in rows],
    }


@app.get("/calls/{llamada_id}", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def llamada_detalle(request: Request, llamada_id: int):
    _require_llamadas()
    llamada = app_state.llamadas.obtener(llamada_id)
    if not llamada:
        raise HTTPException(status_code=404, detail="Llamada no encontrada")
    return JSONResponse(llamada)


# ------------------------------------------------------------------
# Afiliación (GSSI y scan list activos en el radio)
# ------------------------------------------------------------------

@app.get("/afiliacion", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def get_afiliacion(request: Request):
    _require_afiliacion()
    return {
        "gssi":      app_state.afiliacion.gssi,
        "scan_list": app_state.afiliacion.scan_list,
    }


@app.post("/afiliacion/gssi", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def update_gssi(request: Request, update: GSSIUpdate):
    _require_afiliacion()
    try:
        app_state.afiliacion.update_gssi(update.gssi)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok", "gssi": app_state.afiliacion.gssi}


@app.post("/afiliacion/scan-list", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def update_scanlist(request: Request, update: ScanListUpdate):
    _require_afiliacion()
    try:
        app_state.afiliacion.update_scan_list(update.scan_list)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok", "scan_list": app_state.afiliacion.scan_list}


# ------------------------------------------------------------------
# Grupos (catálogo GSSI → nombre)
# ------------------------------------------------------------------

@app.get("/groups", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def listar_grupos(
    request: Request,
    solo_activos: bool = Query(default=True, description="Si true, devuelve solo grupos activos"),
):
    _require_grupos()
    return app_state.grupos.listar(solo_activos=solo_activos)


@app.get("/groups/{gssi}", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def detalle_grupo(request: Request, gssi: int):
    _require_grupos()
    grupos = app_state.grupos.listar(solo_activos=False)
    grupo  = next((g for g in grupos if g["gssi"] == gssi), None)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return grupo


@app.post("/groups", dependencies=[Depends(verify_token)])
@limiter.limit("30/minute")
def upsert_grupo(request: Request, body: GrupoUpsert):
    _require_grupos()
    ok = app_state.grupos.upsert_grupo(
        gssi=body.gssi,
        nombre=body.nombre,
        descripcion=body.descripcion,
        activo=body.activo,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Error guardando el grupo")
    return {"status": "ok", "gssi": body.gssi}


# ------------------------------------------------------------------
# Scan lists
# ------------------------------------------------------------------

@app.get("/scan-lists", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def listar_scan_lists(request: Request):
    _require_grupos()
    return app_state.grupos.listar_scan_lists()
