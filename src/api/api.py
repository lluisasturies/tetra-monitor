import os
import yaml
from fastapi import FastAPI, Header, HTTPException, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

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
DB_USER     = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
API_KEY     = os.getenv("API_KEY")

if not API_KEY:
    raise RuntimeError("API_KEY no definida en .env")

db = Database(
    host=cfg["database"]["host"],
    port=cfg["database"]["port"],
    dbname=cfg["database"]["dbname"],
    user=DB_USER,
    password=DB_PASSWORD,
)

app = FastAPI(title="TETRA Monitor API", version="1.0.0")

# ---------------------------
# Autenticación
# ---------------------------
def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        logger.warning("Intento de acceso con API key inválida")
        raise HTTPException(status_code=401, detail="Unauthorized")

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
    """Endpoint público para healthcheck — sin API key"""
    return {"status": "ok"}

@app.get("/events", dependencies=[Depends(verify_api_key)])
def listar_eventos(limit: int = Query(default=50, ge=1, le=500)):
    eventos = db.listar_eventos(limit)
    return JSONResponse([dict(e) for e in eventos])

@app.get("/events/{evento_id}", dependencies=[Depends(verify_api_key)])
def evento_detalle(evento_id: int):
    evento = db.obtener_evento(evento_id)
    if not evento:
        raise HTTPException(status_code=404, detail="Evento no encontrado")
    return JSONResponse(evento)

@app.post("/update-gssi", dependencies=[Depends(verify_api_key)])
def update_gssi(update: GSSIUpdate):
    scan_config.update_gssi(update.gssi)
    return {"status": "ok", "gssi": scan_config.gssi}

@app.post("/update-scanlist", dependencies=[Depends(verify_api_key)])
def update_scanlist(update: ScanListUpdate):
    scan_config.update_scan_list(update.scan_list)
    return {"status": "ok", "scan_list": scan_config.scan_list}

@app.get("/scan-config", dependencies=[Depends(verify_api_key)])
def get_scan_config():
    return {"gssi": scan_config.gssi, "scan_list": scan_config.scan_list}