"""BO1 — diagnostic préventif. Enveloppes fines des méthodes publiques, plus /overview pour les graphiques."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query

from ..registry import AgentRegistry
from ..schemas import AgentReportResponse, AskRequest
from ..insights import bo1_overview
from .common import _errors, registry, run_report

router = APIRouter(prefix="/api/bo1", tags=["BO1 — diagnostic préventif"])


@router.get("/orders/{order_id}/diagnosis", response_model=AgentReportResponse, summary="Diagnostic préventif d'une commande")
def diagnosis(order_id: str = Path(pattern=r"^[0-9a-fA-F]{32}$"), audit: bool = Query(False, description="affiche aussi l'issue réelle (rétrospectif)"),
              reg: AgentRegistry = Depends(registry)):
    return run_report(reg, "bo1", lambda ag: ag.diagnose(order_id, audit=audit, use_llm=False))


@router.get("/triage", response_model=AgentReportResponse, summary="Commandes d'un mois classées par risque")
def triage(month: str = Query(pattern=r"^20\d{2}-\d{2}$"), target: Literal["late", "poor"] = "late", top_k: int = Query(20, ge=1, le=200),
           audit: bool = False, reg: AgentRegistry = Depends(registry)):
    return run_report(reg, "bo1", lambda ag: ag.triage(month, top_k=top_k, target=target, audit=audit))


@router.post("/ask", response_model=AgentReportResponse, summary="Question libre (routage par mots-clés de BO1)")
def ask(body: AskRequest, audit: bool = False, reg: AgentRegistry = Depends(registry)):
    return run_report(reg, "bo1", lambda ag: ag.ask(body.question, audit=audit))


@router.get("/overview", summary="Données des graphiques de la page BO1 (classement du mois, déciles, États)")
def overview(month: str = Query(pattern=r"^20\d{2}-\d{2}$"), target: Literal["late", "poor"] = "late", top_k: int = Query(15, ge=1, le=100),
             reg: AgentRegistry = Depends(registry)):
    def go():
        with reg.use("bo1") as ag:
            return bo1_overview(ag, month, target, top_k)
    return _errors("bo1", go)
