"""BO2 — voix du client. Enveloppes fines : appels des méthodes publiques existantes, sortie `Report.to_dict()` inchangée."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from ..registry import AgentRegistry
from ..schemas import AgentReportResponse, AskRequest
from .common import _errors, registry, run_report

router = APIRouter(prefix="/api/bo2", tags=["BO2 — voix du client"])


@router.get("/report", response_model=AgentReportResponse, summary="Voix du client pour un mois / État / catégorie")
def report(month: str | None = Query(None, pattern=r"^20\d{2}-\d{2}$"), state: str | None = Query(None, pattern=r"^[A-Z]{2}$"),
           category: str | None = None, focus: str | None = None, sentiment_focus: Literal["negatif", "positif"] = "negatif",
           reg: AgentRegistry = Depends(registry)):
    return run_report(reg, "bo2", lambda ag: ag.report(month, state, category, focus=focus, sentiment_focus=sentiment_focus, use_llm=False))


@router.get("/default-month", summary="Dernier mois avec assez d'avis (méthode publique default_month)")
def default_month(reg: AgentRegistry = Depends(registry)):
    def go():
        with reg.use("bo2") as ag:
            return {"month": ag.default_month()}
    return _errors("bo2", go)


@router.post("/ask", response_model=AgentReportResponse, summary="Question libre (routage de BO2)")
def ask(body: AskRequest, reg: AgentRegistry = Depends(registry)):
    return run_report(reg, "bo2", lambda ag: ag.ask(body.question))
