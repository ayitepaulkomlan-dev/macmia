"""
main.py — API MACMIA
====================
Moteur de recommandation de formations IA / Data / Industrie du Futur
pour les Grandes Écoles IMT (France 2030).

Lancement :
    uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import profil

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s : %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="MACMIA API",
    description="Moteur de recommandation de formations IA & Data — IMT × France 2030",
    version="0.1.0",
)

# Origines autorisées : Vite en dev, plus tout domaine défini par CORS_ORIGINS
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
]
_env_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _env_origins,
    allow_origin_regex=r"https://.*\.ngrok-free\.dev|https://.*\.ngrok\.io",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profil.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "macmia-api", "version": app.version}
