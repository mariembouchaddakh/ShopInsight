"""Exports téléchargeables des audits vendeur (PDF, CSV des preuves)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Path as PathParam, Query, Request
from fastapi.responses import Response

from ..registry import AgentRegistry
from ..llm.analyst import revalidate
from ..reports import evidence_csv, seller_pdf
from ..serialization import evidence_snapshot, jsonable
from .common import _errors, registry

router = APIRouter(prefix="/api/reports", tags=["Rapports"])
SELLER = PathParam(min_length=8, max_length=32, pattern=r"^[0-9a-fA-F]+$")
MONTH = Query(None, pattern=r"^20\d{2}-\d{2}$")


def _audit(reg: AgentRegistry, seller_id: str, month: str | None) -> tuple[dict, list[dict]]:
    def go():
        with reg.use("bo3") as ag:
            rep = ag.audit(seller_id, month, use_llm=False)
            audit = {"report": jsonable(rep.to_dict()), "evidence": evidence_snapshot(ag.log)}
            meta = rep.meta
            hist = ag.alert_history_rows(meta.get("seller_id"), until=meta.get("month"), limit=200)["rows"] if meta.get("seller_id") else []
            return audit, hist
    return _errors("bo3", go)


@router.get("/sellers/{seller_id}.pdf", summary="Rapport d'audit PDF (déterministe + analyse IA validée en option)")
def seller_report_pdf(request: Request, seller_id: str = SELLER, month: str | None = MONTH, include_ai: bool = True,
                      model: Literal["a", "b"] = "a", reg: AgentRegistry = Depends(registry)):
    audit, hist = _audit(reg, seller_id, month)
    meta = audit["report"].get("meta") or {}
    ai = None
    if include_ai and meta.get("seller_id"):
        f = Path(request.app.state.settings.project_dir) / f"data/model/llm_analyses/{meta['seller_id']}_{meta.get('month')}_{model}.json"
        if f.exists():
            ai = revalidate(json.loads(f.read_text(encoding="utf-8")), audit["report"], audit["evidence"])
    pdf = seller_pdf(audit, hist, ai)
    name = f"audit_{(meta.get('seller_id') or seller_id)[:8]}_{meta.get('month', month or '')}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/sellers/{seller_id}/evidence.csv", summary="Preuves de l'audit au format CSV")
def seller_evidence_csv(seller_id: str = SELLER, month: str | None = MONTH, reg: AgentRegistry = Depends(registry)):
    audit, _ = _audit(reg, seller_id, month)
    meta = audit["report"].get("meta") or {}
    name = f"preuves_{(meta.get('seller_id') or seller_id)[:8]}_{meta.get('month', month or '')}.csv"
    return Response(evidence_csv(audit), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})
