import os
import secrets
import bcrypt
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
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

from core.logger import logger  # noqa: E402
from app_state import app_state  # noqa: E402

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
# Startup autonomo
# ------------------------------------------------------------------

def _init_standalone():
    if app_state.pool is not None:
        return

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

    try:
        pool = DBPool(
            host=cfg["database"]["host"],
            port=cfg["database"]["port"],
            dbname=cfg["database"]["dbname"],
            user=os.getenv("DB_USER", ""),
            password=os.getenv("DB_PASSWORD", ""),
        )
    except Exception as e:
        logger.error(f"[API standalone] No se pudo conectar a la BD: {e}")
        return

    llamadas_db = LlamadasDB(pool)
    grupos_db   = GruposDB(pool)
    afiliacion  = AfiliacionConfig(AFILIACION_PATH)

    app_state.pool       = pool
    app_state.llamadas   = llamadas_db
    app_state.grupos     = grupos_db
    app_state.afiliacion = afiliacion

    # Nota: keyword_filter NO se inicializa en modo standalone.
    # app_state.keyword_filter lo establece el daemon PEI al arrancar.
    # Los endpoints /keywords devolveran 503 hasta que el daemon este activo.

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
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _safe_username(username: str) -> str:
    cleaned = username[:32]
    return cleaned if len(username) <= 32 else cleaned + "..."

def _require_llamadas():
    if app_state.llamadas is None:
        raise HTTPException(status_code=503, detail="Servicio no disponible aun")

def _require_afiliacion():
    if app_state.afiliacion is None:
        raise HTTPException(status_code=503, detail="Servicio no disponible aun")

def _require_grupos():
    if app_state.grupos is None:
        raise HTTPException(status_code=503, detail="Servicio no disponible aun")

def _require_keywords():
    if app_state.keyword_filter is None:
        raise HTTPException(
            status_code=503,
            detail="El filtro de keywords no esta disponible. El daemon PEI debe estar activo.",
        )


def _get_db_metrics() -> dict:
    if app_state.llamadas is None:
        return {"calls_today": None, "last_call_at": None}
    try:
        from psycopg2.extras import RealDictCursor
        conn = app_state.pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(*) AS total FROM llamadas WHERE timestamp >= CURRENT_DATE"
                )
                calls_today = cur.fetchone()["total"]
                cur.execute("SELECT MAX(timestamp) AS last_ts FROM llamadas")
                last_ts = cur.fetchone()["last_ts"]
                last_call_at = last_ts.isoformat() if last_ts else None
        finally:
            app_state.pool.putconn(conn)
        return {"calls_today": calls_today, "last_call_at": last_call_at}
    except Exception as e:
        logger.warning(f"[health] No se pudieron obtener metricas de BD: {e}")
        return {"calls_today": None, "last_call_at": None}


# ------------------------------------------------------------------
# JWT
# ------------------------------------------------------------------

def create_access_token(username: str) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_HOURS),
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
            raise HTTPException(status_code=401, detail="Token invalido")
        return user
    except JWTError:
        logger.warning("Intento de acceso con token JWT invalido o expirado")
        raise HTTPException(status_code=401, detail="Token invalido o expirado")


# ------------------------------------------------------------------
# Modelos Pydantic
# ------------------------------------------------------------------

class GSSIUpdate(BaseModel):
    gssi: str

class ScanListUpdate(BaseModel):
    scan_list: str | None = None

class RefreshRequest(BaseModel):
    refresh_token: str

class GrupoUpsert(BaseModel):
    gssi: int
    nombre: str
    activo: bool = True

class CarpetaGrupoEntry(BaseModel):
    gssi: int
    orden: int = 0

class CarpetaUpsert(BaseModel):
    nombre: str
    orden: int = 0
    grupos: list[CarpetaGrupoEntry] = []

class KeywordAdd(BaseModel):
    keyword: str


# ------------------------------------------------------------------
# Health
# ------------------------------------------------------------------

@app.get("/health")
@limiter.limit("30/minute")
def health(request: Request):
    db_ok       = app_state.pool is not None
    pei_ok      = app_state.afiliacion is not None
    radio_ok    = app_state.radio_connected
    telegram_ok = app_state.bot is not None
    streaming   = app_state.streaming_active
    degraded    = not (db_ok and pei_ok and radio_ok)
    status      = "degraded" if degraded else "ok"
    metrics     = _get_db_metrics()

    body = {
        "status":       status,
        "db":           db_ok,
        "pei":          pei_ok,
        "radio":        radio_ok,
        "telegram":     telegram_ok,
        "streaming":    streaming,
        "calls_today":  metrics["calls_today"],
        "last_call_at": metrics["last_call_at"],
    }
    http_status = 503 if degraded else 200
    return JSONResponse(content=body, status_code=http_status)


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
        logger.warning("Intento de refresh con token invalido o ya usado")
        raise HTTPException(status_code=401, detail="Refresh token invalido o expirado")
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
    logger.info("Sesion cerrada correctamente")
    return {"status": "ok"}


# ------------------------------------------------------------------
# Llamadas
# ------------------------------------------------------------------

@app.get("/calls", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def listar_llamadas(
    request: Request,
    limit:  int      = Query(default=50,   ge=1, le=500, description="Resultados por pagina"),
    offset: int      = Query(default=0,    ge=0,         description="Desplazamiento para paginacion"),
    gssi:   int|None = Query(default=None,               description="Filtrar por GSSI (grupo)"),
    ssi:    int|None = Query(default=None,               description="Filtrar por SSI (emisor)"),
    texto:  str|None = Query(default=None,               description="Buscar en transcripcion (contiene)"),
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
# Keywords
# ------------------------------------------------------------------

@app.get("/keywords", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def listar_keywords(request: Request):
    _require_keywords()
    return {"keywords": app_state.keyword_filter.keywords}


@app.post("/keywords", dependencies=[Depends(verify_token)])
@limiter.limit("30/minute")
def anadir_keyword(request: Request, body: KeywordAdd):
    _require_keywords()
    kw = body.keyword.strip()
    if not kw:
        raise HTTPException(status_code=422, detail="La keyword no puede estar vacia")
    added = app_state.keyword_filter.add(kw)
    if not added:
        raise HTTPException(status_code=409, detail=f"La keyword '{kw.lower()}' ya existe")
    return {"status": "ok", "keywords": app_state.keyword_filter.keywords}


@app.delete("/keywords/{keyword}", dependencies=[Depends(verify_token)])
@limiter.limit("30/minute")
def eliminar_keyword(request: Request, keyword: str):
    _require_keywords()
    removed = app_state.keyword_filter.remove(keyword)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Keyword '{keyword.lower()}' no encontrada")
    return {"status": "ok", "keywords": app_state.keyword_filter.keywords}


# ------------------------------------------------------------------
# Afiliacion
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
# Grupos
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
        activo=body.activo,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Error guardando el grupo")
    return {"status": "ok", "gssi": body.gssi}


# ------------------------------------------------------------------
# Carpetas
# ------------------------------------------------------------------

@app.get("/folders", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def listar_carpetas(request: Request):
    _require_grupos()
    return app_state.grupos.listar_carpetas()


@app.get("/folders/{carpeta_id}", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def detalle_carpeta(request: Request, carpeta_id: int):
    _require_grupos()
    carpetas = app_state.grupos.listar_carpetas()
    carpeta  = next((c for c in carpetas if c["id"] == carpeta_id), None)
    if not carpeta:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    return carpeta


@app.post("/folders", dependencies=[Depends(verify_token)])
@limiter.limit("30/minute")
def upsert_carpeta(request: Request, body: CarpetaUpsert):
    _require_grupos()
    carpeta_id = app_state.grupos.upsert_carpeta(
        nombre=body.nombre,
        orden=body.orden,
    )
    if carpeta_id is None:
        raise HTTPException(status_code=500, detail="Error guardando la carpeta")

    ok = app_state.grupos.set_grupos_carpeta(
        carpeta_id=carpeta_id,
        gssi_orden=[{"gssi": g.gssi, "orden": g.orden} for g in body.grupos],
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Error asignando grupos a la carpeta")

    return {"status": "ok", "id": carpeta_id, "nombre": body.nombre}


@app.put("/folders/{carpeta_id}/groups", dependencies=[Depends(verify_token)])
@limiter.limit("30/minute")
def actualizar_grupos_carpeta(request: Request, carpeta_id: int, body: list[CarpetaGrupoEntry]):
    _require_grupos()
    carpetas = app_state.grupos.listar_carpetas()
    if not any(c["id"] == carpeta_id for c in carpetas):
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")

    ok = app_state.grupos.set_grupos_carpeta(
        carpeta_id=carpeta_id,
        gssi_orden=[{"gssi": g.gssi, "orden": g.orden} for g in body],
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Error actualizando grupos de la carpeta")
    return {"status": "ok", "id": carpeta_id}


@app.delete("/folders/{carpeta_id}", dependencies=[Depends(verify_token)])
@limiter.limit("30/minute")
def borrar_carpeta(request: Request, carpeta_id: int):
    _require_grupos()
    ok = app_state.grupos.borrar_carpeta(carpeta_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    return {"status": "ok", "id": carpeta_id}


# ------------------------------------------------------------------
# Scan lists
# ------------------------------------------------------------------

@app.get("/scan-lists", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def listar_scan_lists(request: Request):
    _require_grupos()
    return app_state.grupos.listar_scan_lists()
