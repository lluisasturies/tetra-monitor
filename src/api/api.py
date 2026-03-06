import os
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from src.core.database import Database
import yaml
from typing import List
from pydantic import BaseModel
from pathlib import Path

base_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(base_dir, "../config/config.yaml")

try:
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)
except FileNotFoundError:
    raise FileNotFoundError(f"No se encontró el archivo de configuración: {config_path}")

db = Database(**cfg["database"])
app = FastAPI(title="Tetra Monitor API")

SCAN_CONFIG_PATH = Path("config/scan.yaml")

class ScanConfig:
    def __init__(self):
        self.gssi = ""
        self.scan_list: List[str] = []
        self._load()

    def _load(self):
        if SCAN_CONFIG_PATH.exists():
            with open(SCAN_CONFIG_PATH, "r") as f:
                data = yaml.safe_load(f) or {}
            self.gssi = data.get("gssi", "")
            self.scan_list = data.get("scan_list", [])
        else:
            self.gssi = ""
            self.scan_list = []

    def save(self):
        with open(SCAN_CONFIG_PATH, "w") as f:
            yaml.safe_dump({
                "gssi": self.gssi,
                "scan_list": self.scan_list
            }, f)

    def update_gssi(self, gssi: str):
        self.gssi = gssi
        self.save()

    def update_scan_list(self, scan_list: List[str]):
        self.scan_list = scan_list
        self.save()

scan_config = ScanConfig()

API_KEY = "TU_API_KEY_SECRETA"

def verify_api_key(api_key: str):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

class GSSIUpdate(BaseModel):
    gssi: str

class ScanListUpdate(BaseModel):
    scan_list: List[str]

@app.get("/events")
def listar_eventos(limit: int = 50):
    eventos = db.listar_eventos(limit)
    return JSONResponse(eventos)

@app.get("/events/{id}")
def evento_detalle(id: int):
    eventos = db.listar_eventos(limit=1000)
    for e in eventos:
        if e["id"] == id:
            return JSONResponse(e)
    return JSONResponse({"error": "Evento no encontrado"}, status_code=404)

@app.post("/update-gssi")
def update_gssi(update: GSSIUpdate, x_api_key: str = Header(...)):
    """Actualiza GSSI y lo guarda en config/scan.yaml"""
    verify_api_key(x_api_key)
    scan_config.update_gssi(update.gssi)
    return {"status": "ok", "gssi": scan_config.gssi}

@app.post("/update-scanlist")
def update_scanlist(update: ScanListUpdate, x_api_key: str = Header(...)):
    """Actualiza Scan List y la guarda en config/scan.yaml"""
    verify_api_key(x_api_key)
    scan_config.update_scan_list(update.scan_list)
    return {"status": "ok", "scan_list": scan_config.scan_list}

@app.get("/scan-config")
def get_scan_config(x_api_key: str = Header(...)):
    """Obtiene la configuración actual de GSSI y Scan List"""
    verify_api_key(x_api_key)
    return {"gssi": scan_config.gssi, "scan_list": scan_config.scan_list}