from fastapi import FastAPI
from fastapi.responses import JSONResponse
from database import Database
import yaml

with open("config/config.yaml") as f:
    cfg = yaml.safe_load(f)

db = Database(**cfg["database"])
app = FastAPI()

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