from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..registry import AgentRegistry
from ..schemas import HealthResponse
from .common import registry

router = APIRouter(prefix="/api", tags=["Santé"])


@router.get("/health", response_model=HealthResponse, summary="État de l'API et du chargement des agents (aucun secret)")
def health(request: Request, reg: AgentRegistry = Depends(registry)):
    agents = {k: v for k, v in reg.status.items()}
    status = "degraded" if any(v["state"] == "error" for v in agents.values()) else "ok"
    return {"status": status, "agents": agents, "config": request.app.state.settings.public()}
