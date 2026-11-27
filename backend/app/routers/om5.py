"""FastAPI endpoints for OM5 marketplace monitoring."""
from __future__ import annotations

import json
import time
from copy import deepcopy
from threading import Lock

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ..om5_reports import csv_bytes, report_pdf
from ..serialization import evidence_snapshot, jsonable
from .common import registry

router = APIRouter(prefix="/api/om5", tags=["OM5 — pilotage marketplace"])


_REPORT_CACHE: dict[tuple[str | None, str, bool], tuple[float, dict]] = {}
_CACHE_LOCK = Lock()
_CACHE_TTL_SECONDS = 300


class AskRequest(BaseModel):
    month: str = Field(pattern=r"^20\d{2}-(0[1-9]|1[0-2])$")
    mode: str = Field(default="as_of", pattern=r"^(as_of|retrospective)$")
    include_agents: bool = True


def _agent(request: Request):
    return registry(request).use("om5")


def _run(request: Request, month: str | None, mode: str, include_agents: bool = True) -> dict:
    key = (month, mode, include_agents)
    with _CACHE_LOCK:
        cached = _REPORT_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _CACHE_TTL_SECONDS:
            return deepcopy(cached[1])
    try:
        with _agent(request) as agent:
            report = agent.run(month, mode, include_agents)
            payload = {"agent": "om5", "report": jsonable(report.to_dict()), "markdown": report.to_markdown(),
                       "evidence": evidence_snapshot(agent.log)}
            with _CACHE_LOCK:
                _REPORT_CACHE[key] = (time.monotonic(), deepcopy(payload))
            return payload
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=f"Données manquantes : {exc}") from exc


@router.get("/meta", summary="Périodes et méthodes OM5 disponibles")
def meta(request: Request):
    with _agent(request) as agent:
        return {"default_month": agent.default_month(), "months": agent.store.monthly["purchase_month"].astype(str).tolist(),
                "complete_months": agent.store.monthly.loc[agent.store.monthly["is_complete_period"].astype(bool), "purchase_month"].astype(str).tolist(),
                "modes": ["as_of", "retrospective"], "call_budget": agent.max_calls,
                "detectors": ["robust_z_mad", "two_proportion_normal", "benjamini_hochberg", "wilson_interval"],
                "historical_dataset": "Olist 2016–2018"}


@router.get("/kpis", summary="KPI sourcés pour un mois")
def kpis(request: Request, month: str, mode: str = Query("as_of", pattern="^(as_of|retrospective)$")):
    try:
        with _agent(request) as agent:
            agent.log = type(agent.log)()
            return agent.get_monthly_kpis(month, mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/trends", summary="Historique mensuel complet")
def trends(request: Request, mode: str = Query("as_of", pattern="^(as_of|retrospective)$")):
    with _agent(request) as agent:
        return {"mode": mode, "rows": agent.get_trends(mode)}


@router.get("/anomalies", summary="Anomalies statistiques d'un mois")
def anomalies(request: Request, month: str, mode: str = Query("as_of", pattern="^(as_of|retrospective)$")):
    try:
        with _agent(request) as agent:
            agent.log = type(agent.log)()
            return agent.detect_kpi_anomalies(month, mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/segments", summary="Contributions par État et catégorie")
def segments(request: Request, month: str, metric: str, mode: str = Query("as_of", pattern="^(as_of|retrospective)$")):
    try:
        with _agent(request) as agent:
            agent.log = type(agent.log)()
            return agent.analyze_segments(month, metric, mode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/report", summary="Rapport OM5 déterministe et multi-agent")
def report(request: Request, month: str | None = None, mode: str = Query("as_of", pattern="^(as_of|retrospective)$"), include_agents: bool = True):
    return _run(request, month, mode, include_agents)


@router.post("/ask", summary="Déclencher le workflow OM5 encadré")
def ask(request: Request, body: AskRequest):
    return _run(request, body.month, body.mode, body.include_agents)


@router.get("/report.pdf", summary="Exporter le rapport global en PDF")
def pdf(request: Request, month: str | None = None, mode: str = Query("as_of", pattern="^(as_of|retrospective)$")):
    payload = _run(request, month, mode)
    content = report_pdf(payload)
    name = f"shopinsight-om5-{month or 'latest'}-{mode}.pdf"
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/kpis.csv", summary="Exporter les KPI en CSV")
def kpis_csv(request: Request, month: str, mode: str = Query("as_of", pattern="^(as_of|retrospective)$")):
    with _agent(request) as agent:
        rows = agent.get_monthly_kpis(month, mode)["kpis"]
    return Response(csv_bytes(rows), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="om5-kpis-{month}.csv"'})


@router.get("/evidence.csv", summary="Exporter les preuves en CSV")
def evidence_csv(request: Request, month: str, mode: str = Query("as_of", pattern="^(as_of|retrospective)$")):
    payload = _run(request, month, mode)
    rows = [{**x, "payload": json.dumps(x["payload"], ensure_ascii=False)} for x in payload["evidence"]]
    return Response(csv_bytes(rows), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="om5-evidence-{month}.csv"'})

