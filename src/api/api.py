import os
import yaml
from datetime import datetime, timedelta
from fastapi import FastAPI, Header, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()

from core.database import Database
from core.scan_config import scan_config
from core.logger import logger

# ---------------------------
# Configuración
# ---------------------------
base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, "../../config/config.yaml")

try:
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)
except FileNotFoundError:
    raise FileNotFoundError(f"No se encontró config.yaml en {config_path}")

# Leer credenciales exclusivamente desde .env
DB_USER      = os.getenv("DB_USER", "")
DB_PASSWORD  = os.getenv("DB_PASSWORD", "")
JWT_SECRET   = os.getenv("JWT_SECRET")
API_USER     = os.getenv("API_USER")
API_PASSWORD = os.getenv("API_PASSWORD")

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET no definido en .env")
if not API_USER or not API_PASSWORD:
    raise RuntimeError("API_USER y API_PASSWORD deben estar definidos en .env")

JWT_ALGORITHM   = "HS256"
JWT_EXPIRY_HOURS = 24

db = Database(
    host=cfg["database"]["host"],
    port=cfg["database"]["port"],
    dbname=cfg["database"]["dbname"],
    user=DB_USER,
    password=DB_PASSWORD,
)

app = FastAPI(title="TETRA Monitor API", version="1.0.0")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# ---------------------------
# JWT helpers
# ---------------------------
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

# ---------------------------
# Modelos
# ---------------------------
class GSSIUpdate(BaseModel):
    gssi: str

class ScanListUpdate(BaseModel):
    scan_list: str

# ---------------------------
# Endpoints
# ---------------------------
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

@app.get("/events", dependencies=[Depends(verify_token)])
def listar_eventos(limit: int = Query(default=50, ge=1, le=500)):
    eventos = db.listar_eventos(limit)
    return JSONResponse([dict(e) for e in eventos])

@app.get("/events/{evento_id}", dependencies=[Depends(verify_token)])
def evento_detalle(evento_id: int):
    evento = db.obtener_evento(evento_id)
    if not evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return JSONResponse(evento)

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