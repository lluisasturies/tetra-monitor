import os
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()

from core.scan_config import scan_config
from core.logger import logger
from app_state import app_state

JWT_SECRET   = os.getenv("JWT_SECRET")
API_USER     = os.getenv("API_USER")
API_PASSWORD = os.getenv("API_PASSWORD")

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET no definido en .env")
if not API_USER or not API_PASSWORD:
    raise RuntimeError("API_USER y API_PASSWORD deben estar definidos en .env")

JWT_ALGORITHM    = "HS256"
JWT_EXPIRY_HOURS = 24

app = FastAPI(title="TETRA Monitor API", version="1.0.0")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


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


@app.get("/health")
def health():
    """Endpoint público para healthcheck — sin autenticación"""
    return {"status": "ok"}


@app.post("/auth/token")
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Obtener un token JWT con usuario y contraseña"""
    if form_data.username != API_USER or form_data.password != API_PASSWORD:
        logger.warning(f"Intento de login fallido para usuario '{form_data.username}'")
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    token = create_access_token({"sub": form_data.username})
    logger.info(f"Token JWT generado para '{form_data.username}'")
    return {"access_token": token, "token_type": "bearer"}


@app.get("/calls", dependencies=[Depends(verify_token)])
def listar_llamadas(limit: int = Query(default=50, ge=1, le=500)):
    llamadas = app_state.llamadas.listar(limit)
    return JSONResponse([dict(l) for l in llamadas])


@app.get("/calls/{llamada_id}", dependencies=[Depends(verify_token)])
def llamada_detalle(llamada_id: int):
    llamada = app_state.llamadas.obtener(llamada_id)
    if not llamada:
        raise HTTPException(status_code=404, detail="Llamada no encontrada")
    return JSONResponse(llamada)


@app.post("/update-gssi", dependencies=[Depends(verify_token)])
def update_gssi(update: GSSIUpdate):
    scan_config.update_gssi(update.gssi)
    return {"status": "ok", "gssi": scan_config.gssi}


@app.post("/update-scanlist", dependencies=[Depends(verify_token)])
def update_scanlist(update: ScanListUpdate):
    scan_config.update_scan_list(update.scan_list)
    return {"status": "ok", "scan_list": scan_config.scan_list}


@app.get("/scan-config", dependencies=[Depends(verify_token)])
def get_scan_config():
    return {"gssi": scan_config.gssi, "scan_list": scan_config.scan_list}
