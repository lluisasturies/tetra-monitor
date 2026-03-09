import os
import secrets
import bcrypt
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
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

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="TETRA Monitor API", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def _safe_username(username: str) -> str:
    cleaned = username[:32]
    return cleaned if len(username) <= 32 else cleaned + "…"


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


class GSSIUpdate(BaseModel):
    gssi: str

class ScanListUpdate(BaseModel):
    scan_list: str

class RefreshRequest(BaseModel):
    refresh_token: str


@app.get("/health")
@limiter.limit("30/minute")
def health(request: Request):
    return {"status": "ok"}


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


@app.get("/calls", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def listar_llamadas(request: Request, limit: int = Query(default=50, ge=1, le=500)):
    llamadas = app_state.llamadas.listar(limit)
    return JSONResponse([dict(l) for l in llamadas])


@app.get("/calls/{llamada_id}", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def llamada_detalle(request: Request, llamada_id: int):
    llamada = app_state.llamadas.obtener(llamada_id)
    if not llamada:
        raise HTTPException(status_code=404, detail="Llamada no encontrada")
    return JSONResponse(llamada)


@app.post("/update-gssi", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def update_gssi(request: Request, update: GSSIUpdate):
    try:
        app_state.scan_config.update_gssi(update.gssi)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok", "gssi": app_state.scan_config.gssi}


@app.post("/update-scanlist", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def update_scanlist(request: Request, update: ScanListUpdate):
    try:
        app_state.scan_config.update_scan_list(update.scan_list)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"status": "ok", "scan_list": app_state.scan_config.scan_list}


@app.get("/scan-config", dependencies=[Depends(verify_token)])
@limiter.limit("60/minute")
def get_scan_config(request: Request):
    return {"gssi": app_state.scan_config.gssi, "scan_list": app_state.scan_config.scan_list}
