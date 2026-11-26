"""Couche IA (OpenRouter, modèles gratuits uniquement) : analyse et assistant vendeur, sur les preuves déterministes de BO3.

L'audit est calculé par BO3 (sous verrou), puis le LLM est appelé HORS verrou. Si le LLM est indisponible (clé absente, quota,
modèle non gratuit…), la réponse est une erreur 503 explicite : l'audit déterministe (/api/bo3/sellers/{id}/audit) reste complet.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..llm.analyst import SECTION_TITLES, analyse, chat, market_chat
from ..llm.fallback import answer_without_llm
from ..llm.provider import FailoverFreeProvider, LLMError, fetch_catalog, is_free
from ..registry import AgentRegistry
from ..serialization import evidence_snapshot, jsonable
from .common import EvidenceLog, _errors, registry

router = APIRouter(prefix="/api/llm", tags=["IA — analyse vendeur (OpenRouter gratuit)"])
ModelSlot = Literal["a", "b"]
STATUS = {"no_key": 503, "not_free": 409, "rate_limited": 429, "quota_exhausted": 429, "unavailable": 503, "bad_response": 502, "substituted": 502, "not_zero_cost": 409}


def model_id(request: Request, slot: str) -> str:
    s = request.app.state.settings
    mid = {"a": s.llm_model_a, "b": s.llm_model_b, "judge": s.llm_judge_model}[slot]
    if not mid:
        raise HTTPException(503, f"Aucun modèle configuré pour « {slot} » (LLM_MODEL_A / LLM_MODEL_B / LLM_JUDGE_MODEL dans .env) ; l'audit déterministe reste disponible.")
    return mid


def provider_for(request: Request, slot: str) -> FailoverFreeProvider:
    """Modèle du créneau demandé, puis repli ordonné sur LLM_FALLBACK_MODELS ; chaque candidat repasse tous les garde-fous de gratuité."""
    s = request.app.state.settings
    base = Path(s.project_dir) / "data/model"
    return FailoverFreeProvider(s.openrouter_api_key, [model_id(request, slot), *s.llm_fallback_models], cache_dir=base / "llm_cache",
                                call_log=base / "llm_calls.jsonl")


def analyses_dir(request: Request) -> Path:
    return Path(request.app.state.settings.project_dir) / "data/model/llm_analyses"


def deterministic_audit(reg: AgentRegistry, seller_id: str, month: str | None) -> tuple[dict, list[dict], str, str]:
    def go():
        with reg.use("bo3") as ag:
            rep = ag.audit(seller_id, month, use_llm=False)
            return jsonable(rep.to_dict()), evidence_snapshot(ag.log), rep.meta.get("seller_id"), rep.meta.get("month")
    return _errors("bo3", go)


def llm_http_error(e: LLMError) -> HTTPException:
    return HTTPException(STATUS.get(e.kind, 503), f"IA indisponible ({e.kind}) : {e}. L'audit déterministe reste disponible.")


class AnalysisRequest(BaseModel):
    month: str | None = Field(None, pattern=r"^20\d{2}-\d{2}$")
    model: ModelSlot = "a"


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    month: str | None = Field(None, pattern=r"^20\d{2}-\d{2}$")
    model: ModelSlot = "a"
    question: str = Field(min_length=3, max_length=600)
    history: list[ChatTurn] = Field(default_factory=list, max_length=12)


@router.get("/status", summary="Modèles configurés, gratuité vérifiée en direct, clé présente (sans la montrer)")
def status(request: Request):
    s = request.app.state.settings
    out = {"key_configured": bool(s.openrouter_api_key), "budget_usd": s.llm_budget_usd, "free_only": s.llm_free_only, "models": {}}
    try:
        cat = fetch_catalog(provider_for(request, "a").client) if (s.llm_model_a or s.llm_model_b) else {}
    except Exception as e:  # noqa: BLE001
        cat, out["catalog_error"] = {}, type(e).__name__
    for slot in ("a", "b", "judge"):
        mid = {"a": s.llm_model_a, "b": s.llm_model_b, "judge": s.llm_judge_model}[slot]
        m = cat.get(mid) if mid else None
        out["models"][slot] = {"id": mid, "in_catalog": m is not None, "free_verified": bool(m and is_free(m) and mid.endswith(":free")),
                               "context_length": m.get("context_length") if m else None}
    out["fallbacks"] = [{"id": mid, "in_catalog": mid in cat, "free_verified": bool(mid in cat and is_free(cat[mid]) and mid.endswith(":free"))}
                        for mid in s.llm_fallback_models]
    out["usable"] = out["key_configured"] and any(v["free_verified"] for k, v in out["models"].items() if k in ("a", "b"))
    return out


@router.post("/sellers/{seller_id}/analysis", summary="Analyse IA validée d'un vendeur (chiffres et preuves contrôlés)")
def seller_analysis(seller_id: str, body: AnalysisRequest, request: Request, reg: AgentRegistry = Depends(registry)):
    if not re.fullmatch(r"[0-9a-fA-F]{8,32}", seller_id):
        raise HTTPException(422, "identifiant vendeur invalide")
    report, evidence, sid, month = deterministic_audit(reg, seller_id, body.month)
    try:
        res = analyse(provider_for(request, body.model), report, evidence)
    except LLMError as e:
        raise llm_http_error(e) from e
    out = {"seller_id": sid, "month": month, "slot": body.model, "section_titles": SECTION_TITLES, **res.to_dict(),
           "disclaimer": "Contenu rédigé par IA à partir des seules preuves déterministes ; chiffres et identifiants vérifiés automatiquement ; "
                         "les hypothèses ne sont pas confirmées."}
    d = analyses_dir(request)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}_{month}_{body.model}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


@router.post("/sellers/{seller_id}/chat", summary="Question sur un vendeur (réponse validée contre les preuves)")
def seller_chat(seller_id: str, body: ChatRequest, request: Request, reg: AgentRegistry = Depends(registry)):
    if not re.fullmatch(r"[0-9a-fA-F]{8,32}", seller_id):
        raise HTTPException(422, "identifiant vendeur invalide")
    report, evidence, sid, month = deterministic_audit(reg, seller_id, body.month)
    try:
        res = chat(provider_for(request, body.model), report, evidence, [t.model_dump() for t in body.history], body.question)
    except LLMError as e:
        # quota épuisé, modèles indisponibles, clé absente : réponse factuelle tirée des preuves plutôt qu'une erreur
        res = answer_without_llm(body.question, evidence, "seller") | {"fallback_reason": e.kind}
    return {"seller_id": sid, "month": month, **res}


def marketplace_evidence(reg: AgentRegistry, month: str | None) -> tuple[list[dict], str]:
    """Preuves « marketplace » du mois (résumé, alertes prioritaires, catégories), calculées par BO3 sous verrou."""
    def go():
        with reg.use("bo3") as ag:
            ag.log = EvidenceLog()
            res = ag.marketplace_brief(month)
            return evidence_snapshot(ag.log), res["categories"]["decision_month"]
    return _errors("bo3", go)


@router.post("/chat", summary="Assistant marketplace (alertes prioritaires, catégories) — réponse validée contre les preuves")
def marketplace_chat(body: ChatRequest, request: Request, reg: AgentRegistry = Depends(registry)):
    evidence, month = marketplace_evidence(reg, body.month)
    try:
        res = market_chat(provider_for(request, body.model), evidence, month, [t.model_dump() for t in body.history], body.question)
    except LLMError as e:
        res = answer_without_llm(body.question, evidence, "market") | {"fallback_reason": e.kind}
    return {"scope": "marketplace", "month": month, **res}
