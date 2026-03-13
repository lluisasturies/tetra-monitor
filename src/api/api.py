import os
import bcrypt
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from importlib.metadata import version as pkg_version, PackageNotFoundError
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from dotenv import load_dotenv
from jose import JWTError, jwt
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

load_dotenv()

from core.logger import logger  # noqa: E402
from app_state import app_state  # noqa: E402

try:
    _API_VERSION = pkg_version("tetra-monitor")
except PackageNotFoundError:
    _API_VERSION = "dev"

JWT_SECRET        = os.getenv("JWT_SECRET")
API_USER          = os.getenv("API_USER", "")
API_PASSWORD_HASH = os.getenv("API_PASSWORD_HASH", "").encode()

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET no definido en .env")

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
    from db.usuarios import UsuariosDB
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
    usuarios_db = UsuariosDB(pool)
    afiliacion  = AfiliacionConfig(AFILIACION_PATH)

    app_state.pool       = pool
    app_state.llamadas   = llamadas_db
    app_state.grupos     = grupos_db
    app_state.usuarios   = usuarios_db
    app_state.afiliacion = afiliacion

    grupos_db.seed_from_yaml(GRUPOS_PATH)
    if API_USER and API_PASSWORD_HASH:
        usuarios_db.seed_admin_desde_env(API_USER, API_PASSWORD_HASH.decode())

    logger.info("[API standalone] Dependencias inicializadas correctamente")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_standalone()
    yield


# ------------------------------------------------------------------
# App
# ------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="TETRA Monitor API", version=_API_VERSION, lifespan=lifespan)
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


def _require(attr: str, detail: str | None = None) -> None:
    """
    Lanza HTTP 503 si app_state.<attr> es None.
    """
    if getattr(app_state, attr) is None:
        raise HTTPException(
            status_code=503,
            detail=detail or "Servicio no disponible aun",
        )


def _require_keywords():
    if app_state.keyword_filter is None:
        raise HTTPException(
            status_code=503,
            detail="El filtro de keywords no esta disponible. El daemon PEI debe estar activo.",
        )


# ------------------------------------------------------------------
# JWT y autorizacion por rol
# ------------------------------------------------------------------

def _create_access_token(usuario_id: int, username: str, rol: str) -> str:
    payload = {
        "sub": username,
        "uid": usuario_id,
        "rol": rol,
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _verify_token(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Verifica el JWT y devuelve el payload completo: {sub, uid, rol}.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if not payload.get("sub"):
            raise HTTPException(status_code=401, detail="Token invalido")
        return payload
    except JWTError:
        logger.warning("Intento de acceso con token JWT invalido o expirado")
        raise HTTPException(status_code=401, detail="Token invalido o expirado")


def _require_rol(*roles: str):
    """
    Fabrica de dependencias FastAPI que exige que el usuario tenga
    al menos uno de los roles indicados.

    Uso:
        @app.post("/users", dependencies=[Depends(_require_rol("admin"))])
    """
    def _check(payload: dict = Depends(_verify_token)):
        if payload.get("rol") not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Permiso insuficiente. Se requiere rol: {' o '.join(roles)}",
            )
        return payload
    return _check


# Dependencias de conveniencia para los tres niveles de acceso
_any_user    = Depends(_verify_token)
_operator_up = Depends(_require_rol("admin", "operator"))
_admin_only  = Depends(_require_rol("admin"))


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

class UsuarioCreate(BaseModel):
    username: str
    password: str
    rol: str = "viewer"
    email: str | None = None

    @field_validator("rol")
    @classmethod
    def _rol_valido(cls, v: str) -> str:
        from db.usuarios import ROLES
        if v not in ROLES:
            raise ValueError(f"Rol invalido. Opciones: {', '.join(ROLES)}")
        return v

    @field_validator("username")
    @classmethod
    def _username_valido(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 64:
            raise ValueError("username debe tener entre 1 y 64 caracteres")
        return v

    @field_validator("password")
    @classmethod
    def _password_valido(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contrasena debe tener al menos 8 caracteres")
        return v

class UsuarioUpdate(BaseModel):
    email: str | None = None
    rol: str | None = None
    activo: bool | None = None
    password: str | None = None

    @field_validator("rol")
    @classmethod
    def _rol_valido(cls, v: str | None) -> str | None:
        if v is None:
            return v
        from db.usuarios import ROLES
        if v not in ROLES:
            raise ValueError(f"Rol invalido. Opciones: {', '.join(ROLES)}")
        return v

    @field_validator("password")
    @classmethod
    def _password_valido(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("La contrasena debe tener al menos 8 caracteres")
        return v


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

    metrics = (
        app_state.llamadas.get_health_metrics()
        if app_state.llamadas
        else {"calls_today": None, "last_call_at": None}
    )

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
    return JSONResponse(content=body, status_code=503 if degraded else 200)


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------

@app.post("/auth/token")
@limiter.limit("5/minute")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Autenticacion: busca el usuario en BD.
    """
    _require("usuarios", "Sistema de usuarios no disponible")
    usuario = app_state.usuarios.obtener_por_username(form_data.username)

    # Comprobacion en tiempo constante para evitar user enumeration
    if usuario is None or not usuario.get("activo", False):
        bcrypt.checkpw(b"dummy", bcrypt.hashpw(b"dummy", bcrypt.gensalt()))
        logger.warning(f"Login fallido para '{_safe_username(form_data.username)}'")
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    if not bcrypt.checkpw(form_data.password.encode(), usuario["password_hash"].encode()):
        logger.warning(f"Login fallido para '{_safe_username(form_data.username)}'")
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    app_state.usuarios.marcar_login(usuario["id"])
    access_token  = _create_access_token(usuario["id"], usuario["username"], usuario["rol"])
    refresh_token = app_state.usuarios.crear_refresh_token(
        usuario["id"], days=REFRESH_TOKEN_DAYS
    )

    logger.info(f"Login correcto para '{_safe_username(usuario['username'])}' (rol={usuario['rol']})")
    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TOKEN_HOURS * 3600,
    }


@app.post("/auth/refresh")
@limiter.limit("10/minute")
def refresh(request: Request, body: RefreshRequest):
    _require("usuarios", "Sistema de usuarios no disponible")
    usuario = app_state.usuarios.consumir_refresh_token(body.refresh_token)
    if not usuario:
        raise HTTPException(status_code=401, detail="Refresh token invalido o expirado")

    new_refresh  = app_state.usuarios.crear_refresh_token(usuario["id"], days=REFRESH_TOKEN_DAYS)
    access_token = _create_access_token(usuario["id"], usuario["username"], usuario["rol"])
    logger.info(f"Token renovado para '{_safe_username(usuario['username'])}'")
    return {
        "access_token":  access_token,
        "refresh_token": new_refresh,
        "token_type":    "bearer",
        "expires_in":    ACCESS_TOKEN_HOURS * 3600,
    }


@app.post("/auth/logout")
@limiter.limit("10/minute")
def logout(request: Request, body: RefreshRequest, payload: dict = _any_user):
    if app_state.usuarios:
        app_state.usuarios.revocar_todos_tokens(payload["uid"])
    logger.info(f"Sesion cerrada para '{_safe_username(payload['sub'])}'")
    return {"status": "ok"}


# ------------------------------------------------------------------
# Usuarios (solo admin)
# ------------------------------------------------------------------

@app.get("/users", dependencies=[_admin_only])
@limiter.limit("30/minute")
def listar_usuarios(request: Request):
    _require("usuarios")
    return app_state.usuarios.listar()


@app.get("/users/me")
@limiter.limit("60/minute")
def perfil_propio(request: Request, payload: dict = _any_user):
    _require("usuarios")
    usuario = app_state.usuarios.obtener_por_id(payload["uid"])
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@app.get("/users/{usuario_id}", dependencies=[_admin_only])
@limiter.limit("30/minute")
def detalle_usuario(request: Request, usuario_id: int):
    _require("usuarios")
    usuario = app_state.usuarios.obtener_por_id(usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@app.post("/users", dependencies=[_admin_only])
@limiter.limit("10/minute")
def crear_usuario(request: Request, body: UsuarioCreate):
    _require("usuarios")
    nuevo = app_state.usuarios.crear(
        username=body.username,
        password=body.password,
        rol=body.rol,
        email=body.email,
    )
    if not nuevo:
        raise HTTPException(status_code=409, detail="El usuario o email ya existe")
    logger.info(f"[API] Usuario creado: '{body.username}' (rol={body.rol})")
    return nuevo


@app.put("/users/{usuario_id}", dependencies=[_admin_only])
@limiter.limit("10/minute")
def actualizar_usuario(request: Request, usuario_id: int, body: UsuarioUpdate):
    _require("usuarios")
    campos = {k: v for k, v in body.model_dump().items() if v is not None}
    if not campos:
        raise HTTPException(status_code=422, detail="No se han proporcionado campos a actualizar")
    actualizado = app_state.usuarios.actualizar(usuario_id, **campos)
    if not actualizado:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return actualizado


@app.delete("/users/{usuario_id}", dependencies=[_admin_only])
@limiter.limit("10/minute")
def desactivar_usuario(request: Request, usuario_id: int, payload: dict = _admin_only):
    """
    Soft-delete: marca el usuario como inactivo y revoca todos sus tokens.
    Un admin no puede desactivarse a si mismo.
    """
    _require("usuarios")
    if usuario_id == payload["uid"]:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propio usuario")
    actualizado = app_state.usuarios.actualizar(usuario_id, activo=False)
    if not actualizado:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    app_state.usuarios.revocar_todos_tokens(usuario_id)
    logger.info(f"[API] Usuario id={usuario_id} desactivado")
    return {"status": "ok", "id": usuario_id}


# ------------------------------------------------------------------
# Llamadas  (viewer+)
# ------------------------------------------------------------------

@app.get("/calls", dependencies=[_any_user])
@limiter.limit("60/minute")
def listar_llamadas(
    request: Request,
    limit:  int      = Query(default=50,   ge=1, le=500),
    offset: int      = Query(default=0,    ge=0),
    gssi:   int|None = Query(default=None),
    ssi:    int|None = Query(default=None),
    texto:  str|None = Query(default=None),
):
    _require("llamadas")
    rows, total = app_state.llamadas.listar_filtrado(
        limit=limit, offset=offset, gssi=gssi, ssi=ssi, texto=texto
    )
    return {"total": total, "limit": limit, "offset": offset,
            "results": [dict(r) for r in rows]}


@app.get("/calls/{llamada_id}", dependencies=[_any_user])
@limiter.limit("60/minute")
def llamada_detalle(request: Request, llamada_id: int):
    _require("llamadas")
    llamada = app_state.llamadas.obtener(llamada_id)
    if not llamada:
        raise HTTPException(status_code=404, detail="Llamada no encontrada")
    return JSONResponse(llamada)


# ------------------------------------------------------------------
# Keywords  (operator+)
# ------------------------------------------------------------------

@app.get("/keywords", dependencies=[_any_user])
@limiter.limit("60/minute")
def listar_keywords(request: Request):
    _require_keywords()
    return {"keywords": app_state.keyword_filter.keywords}


@app.post("/keywords", dependencies=[_operator_up])
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


@app.delete("/keywords/{keyword}", dependencies=[_operator_up])
@limiter.limit("30/minute")
def eliminar_keyword(request: Request, keyword: str):
    _require_keywords()
    removed = app_state.keyword_filter.remove(keyword)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Keyword '{keyword.lower()}' no encontrada")
    return {"status": "ok", "keywords": app_state.keyword_filter.keywords}


# ------------------------------------------------------------------
# Afiliacion  (operator+)
# ------------------------------------------------------------------

@app.get("/afiliacion", dependencies=[_any_user])
@limiter.limit("60/minute")
def get_afiliacion(request: Request):
    _require("afiliacion")
    return {"gssi": app_state.afiliacion.gssi, "scan_list": app_state.afiliacion.scan_list}


@app.post("/afiliacion/gssi", dependencies=[_operator_up])
@limiter.limit("60/minute")
def update_gssi(request: Request, update: GSSIUpdate):
    _require("afiliacion")
    try:
        app_state.afiliacion.update_gssi(update.gssi)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok", "gssi": app_state.afiliacion.gssi}


@app.post("/afiliacion/scan-list", dependencies=[_operator_up])
@limiter.limit("60/minute")
def update_scanlist(request: Request, update: ScanListUpdate):
    _require("afiliacion")
    try:
        app_state.afiliacion.update_scan_list(update.scan_list)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok", "scan_list": app_state.afiliacion.scan_list}


# ------------------------------------------------------------------
# Grupos  (viewer+ para lectura, operator+ para escritura)
# ------------------------------------------------------------------

@app.get("/groups", dependencies=[_any_user])
@limiter.limit("60/minute")
def listar_grupos(request: Request,
                  solo_activos: bool = Query(default=True)):
    _require("grupos")
    return app_state.grupos.listar(solo_activos=solo_activos)


@app.get("/groups/{gssi}", dependencies=[_any_user])
@limiter.limit("60/minute")
def detalle_grupo(request: Request, gssi: int):
    _require("grupos")
    grupos = app_state.grupos.listar(solo_activos=False)
    grupo  = next((g for g in grupos if g["gssi"] == gssi), None)
    if not grupo:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return grupo


@app.post("/groups", dependencies=[_operator_up])
@limiter.limit("30/minute")
def upsert_grupo(request: Request, body: GrupoUpsert):
    _require("grupos")
    ok = app_state.grupos.upsert_grupo(gssi=body.gssi, nombre=body.nombre, activo=body.activo)
    if not ok:
        raise HTTPException(status_code=500, detail="Error guardando el grupo")
    return {"status": "ok", "gssi": body.gssi}


# ------------------------------------------------------------------
# Carpetas  (viewer+ para lectura, operator+ para escritura)
# ------------------------------------------------------------------

@app.get("/folders", dependencies=[_any_user])
@limiter.limit("60/minute")
def listar_carpetas(request: Request):
    _require("grupos")
    return app_state.grupos.listar_carpetas()


@app.get("/folders/{carpeta_id}", dependencies=[_any_user])
@limiter.limit("60/minute")
def detalle_carpeta(request: Request, carpeta_id: int):
    _require("grupos")
    carpetas = app_state.grupos.listar_carpetas()
    carpeta  = next((c for c in carpetas if c["id"] == carpeta_id), None)
    if not carpeta:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    return carpeta


@app.post("/folders", dependencies=[_operator_up])
@limiter.limit("30/minute")
def upsert_carpeta(request: Request, body: CarpetaUpsert):
    _require("grupos")
    carpeta_id = app_state.grupos.upsert_carpeta(nombre=body.nombre, orden=body.orden)
    if carpeta_id is None:
        raise HTTPException(status_code=500, detail="Error guardando la carpeta")
    ok = app_state.grupos.set_grupos_carpeta(
        carpeta_id=carpeta_id,
        gssi_orden=[{"gssi": g.gssi, "orden": g.orden} for g in body.grupos],
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Error asignando grupos a la carpeta")
    return {"status": "ok", "id": carpeta_id, "nombre": body.nombre}


@app.put("/folders/{carpeta_id}/groups", dependencies=[_operator_up])
@limiter.limit("30/minute")
def actualizar_grupos_carpeta(request: Request, carpeta_id: int,
                              body: list[CarpetaGrupoEntry]):
    _require("grupos")
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


@app.delete("/folders/{carpeta_id}", dependencies=[_operator_up])
@limiter.limit("30/minute")
def borrar_carpeta(request: Request, carpeta_id: int):
    _require("grupos")
    ok = app_state.grupos.borrar_carpeta(carpeta_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")
    return {"status": "ok", "id": carpeta_id}


# ------------------------------------------------------------------
# Scan lists  (viewer+)
# ------------------------------------------------------------------

@app.get("/scan-lists", dependencies=[_any_user])
@limiter.limit("60/minute")
def listar_scan_lists(request: Request):
    _require("grupos")
    return app_state.grupos.listar_scan_lists()
