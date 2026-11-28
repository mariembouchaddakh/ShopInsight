"""API ShopInsight (FastAPI).

Lancer depuis la racine du dépôt :
    pip install -r requirements.txt -r requirements-agents.txt -r requirements-api.txt
    uvicorn backend.app.main:app --port 8000
Documentation interactive : http://localhost:8000/docs (OpenAPI : /openapi.json).

BO1 et BO2 sont appelés uniquement via leurs méthodes publiques existantes ; leur sortie (Report.to_dict()) est renvoyée telle quelle.
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import load_settings
from .logging_setup import setup_logging
from .registry import AgentRegistry
from .routers import bo1, bo2, bo3, bo4, health, llm, om5, reports

log = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    app.state.settings = settings
    app.state.registry = AgentRegistry(settings)
    log.info("démarrage", extra={"path": str(settings.project_dir)})
    if settings.warmup:
        app.state.registry.warmup()
    yield


app = FastAPI(
    title="ShopInsight API",
    version="0.3.0",
    description="Agents REHEARSE sur les données Olist : BO1 diagnostic préventif, BO2 voix du client, BO3 audit vendeur. "
                "Tous les chiffres viennent d'outils déterministes ; chaque réponse renvoie ses preuves (identifiants d'évidence).",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=list(load_settings().cors_origins), allow_methods=["GET", "POST"], allow_headers=["*"])


@app.middleware("http")
async def access_log(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    t0 = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("erreur non gérée", extra={"request_id": rid, "method": request.method, "path": request.url.path})
        response = JSONResponse({"detail": "Erreur interne (voir les journaux du serveur)."}, status_code=500)
    ms = round((time.perf_counter() - t0) * 1000, 1)
    response.headers["x-request-id"] = rid
    log.info("requête", extra={"request_id": rid, "method": request.method, "path": request.url.path, "status": response.status_code, "duration_ms": ms})
    return response


for r in (health.router, bo1.router, bo2.router, bo3.router, bo4.router, om5.router, llm.router, reports.router):
    app.include_router(r)
