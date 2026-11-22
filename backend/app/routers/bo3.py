"""BO3 — audit vendeur : vues d'ensemble, alertes, audits et outils de preuve (sorties de l'agent SellerAuditAgent)."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Path, Query

from ..registry import AgentRegistry
from ..schemas import AgentReportResponse, AskRequest, ToolResponse
from ..serialization import jsonable
from .common import _errors, registry, run_report, run_tool

router = APIRouter(prefix="/api/bo3", tags=["BO3 — audit vendeur"])

MONTH = Query(None, pattern=r"^20\d{2}-\d{2}$", description="Mois de décision AAAA-MM (fin de mois) ; défaut : dernier mois complet")
SELLER = Path(min_length=8, max_length=32, pattern=r"^[0-9a-fA-F]+$", description="identifiant vendeur ou ses 8 premiers caractères")
Metric = Literal["late", "poor", "handover"]


@router.get("/meta", summary="Mois disponibles, indicateurs, réglages et performance du modèle")
def meta(reg: AgentRegistry = Depends(registry)):
    def go():
        with reg.use("bo3") as ag:
            import sys
            from ..config import ROOT
            sys.path.insert(0, str(ROOT / "src"))
            from agents.bo3_sellers import ALL_DECISION_MONTHS, METRIC_LABEL, SPLIT_MONTHS, VALID_FOLDS
            from agents.category_labels import CATEGORY_FR
            card = ag.card
            last = ag.default_month()
            return jsonable({"default_month": last, "decision_months": [m for m in ALL_DECISION_MONTHS if m <= last],
                             "metrics": {m: METRIC_LABEL[m] for m in ag.metrics}, "trained": ag.trained,
                             "reference": card.get("peer_label"), "detection": card.get("detection"), "severity_rule": card.get("severity_rule"),
                             "test_summary": card.get("test_summary"), "validation": card.get("validation") or {"folds": VALID_FOLDS, "test": SPLIT_MONTHS["test"]},
                             "model_created": card.get("created"), "category_labels": CATEGORY_FR})
    return _errors("bo3", go)


def _overview(month, alerted_only, q, limit, seller_state, region, main_category, segment, alert_status, severity, trend, reg):
    return run_tool(reg, "bo3", "sellers_overview",
                    lambda ag: ag.sellers_overview(month, alerted_only, q, limit, seller_state=seller_state, region=region, main_category=main_category,
                                                   segment=segment, alert_status=alert_status, severity=severity, trend=trend))


@router.get("/overview", response_model=ToolResponse, summary="Tableau des vendeurs du mois (taux, alertes, sévérité, points forts), filtrable")
@router.get("/sellers", response_model=ToolResponse, summary="Liste filtrable des vendeurs évalués (alias de /overview)")
def overview(month: str | None = MONTH, alerted_only: bool = False,
             q: str | None = Query(None, max_length=64, description="préfixe d'identifiant ou catégorie"),
             limit: int = Query(200, ge=1, le=5000),
             seller_state: str | None = Query(None, pattern=r"^[A-Za-z]{2}$", description="État du vendeur (ex. SP)"),
             region: str | None = Query(None, max_length=32, description="segment régional : Sudeste, Sul, autres régions"),
             main_category: str | None = Query(None, max_length=64, description="catégorie principale"),
             segment: str | None = Query(None, max_length=32, description="segment de volume : petit volume, volume moyen, grand volume"),
             alert_status: Literal["any", "level", "trend", "none"] | None = None,
             severity: Literal["élevée", "moyenne", "faible"] | None = None,
             trend: Literal["degradation", "stable"] | None = None,
             reg: AgentRegistry = Depends(registry)):
    return _overview(month, alerted_only, q, limit, seller_state and seller_state.upper(), region, main_category, segment, alert_status, severity, trend, reg)


@router.get("/marketplace", response_model=ToolResponse, summary="Évolution mensuelle de la marketplace (référence, vendeurs évaluables, alertes)")
def marketplace(reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo3", "marketplace_overview", lambda ag: ag.marketplace_overview())


@router.get("/brief", response_model=ToolResponse, summary="Synthèse marketplace du mois : alertes prioritaires et catégories les plus touchées")
def brief(month: str | None = MONTH, reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo3", "marketplace_brief", lambda ag: ag.marketplace_brief(month))


@router.get("/market-map", response_model=ToolResponse, summary="Carte du marché : vendeurs projetés par profil d'activité et familles (descriptif)")
def market_map(month: str | None = MONTH, groups: int = Query(5, ge=3, le=10), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo3", "market_map", lambda ag: ag.market_map(month, groups))


@router.get("/state-alerts", response_model=ToolResponse, summary="Retards anormaux d'un vendeur vers un État de destination (signal descriptif)")
def state_alerts(month: str | None = MONTH, top_k: int = Query(50, ge=1, le=500), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo3", "state_late_alerts", lambda ag: ag.state_late_alerts(month, top_k))


@router.get("/call-list", response_model=ToolResponse, summary="Vendeurs à appeler cette semaine : motif, e-mail et script d'appel pré-remplis")
def call_list(month: str | None = MONTH, top_k: int = Query(10, ge=1, le=30), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo3", "call_list", lambda ag: ag.call_list(month, top_k))


@router.get("/market-map/trends", response_model=ToolResponse, summary="Évolution mensuelle de chaque famille du marché")
def market_trends(month: str | None = MONTH, n_months: int = Query(6, ge=2, le=12), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo3", "market_family_trends", lambda ag: ag.market_family_trends(month, n_months))


@router.get("/geo/basemap", summary="Fond de carte du Brésil tiré des données (centroïdes postaux regroupés)")
def basemap(reg: AgentRegistry = Depends(registry)):
    def go():
        with reg.use("bo3") as ag:
            return ag.geo_basemap()
    return _errors("bo3", go)


@router.get("/alerts", response_model=ToolResponse, summary="Vendeurs en alerte (triés par sévérité)")
def alerts(month: str | None = MONTH, metric: Metric | None = None, top_k: int = Query(50, ge=1, le=500), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo3", "list_alerts", lambda ag: ag.list_alerts(month, metric, top_k))


@router.get("/alerts/report", response_model=AgentReportResponse, summary="Rapport « vendeurs à investiguer »")
def alerts_report(month: str | None = MONTH, metric: Metric | None = None, top_k: int = Query(15, ge=1, le=100), reg: AgentRegistry = Depends(registry)):
    return run_report(reg, "bo3", lambda ag: ag.alerts_report(month, metric, top_k))


@router.get("/alert-history", response_model=ToolResponse, summary="Historique des alertes (nouvelle / en cours / résolue)")
def alert_history(seller_id: str | None = Query(None, min_length=8, max_length=32), metric: Metric | None = None,
                  family: Literal["level", "trend"] | None = None, status: Literal["new", "ongoing", "resolved"] | None = None,
                  month: str | None = MONTH, until: str | None = Query(None, pattern=r"^20\d{2}-\d{2}$"), limit: int = Query(500, ge=1, le=5000),
                  reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo3", "alert_history", lambda ag: ag.alert_history_rows(seller_id, metric, family, status, month, until, limit))


@router.get("/sellers/{seller_id}/audit", response_model=AgentReportResponse, summary="Audit complet d'un vendeur")
def audit(seller_id: str = SELLER, month: str | None = MONTH, metric: Metric | None = None, reg: AgentRegistry = Depends(registry)):
    return run_report(reg, "bo3", lambda ag: ag.audit(seller_id, month, metric, use_llm=False))


def _tool_route(path: str, tool: str, summary: str, with_metric: bool = False):
    if with_metric:
        @router.get(f"/sellers/{{seller_id}}/{path}", response_model=ToolResponse, summary=summary, name=tool)
        def endpoint(seller_id: str = SELLER, month: str | None = MONTH, metric: Metric = "late", reg: AgentRegistry = Depends(registry)):
            return run_tool(reg, "bo3", tool, lambda ag: getattr(ag, tool)(seller_id, month, metric))
    else:
        @router.get(f"/sellers/{{seller_id}}/{path}", response_model=ToolResponse, summary=summary, name=tool)
        def endpoint(seller_id: str = SELLER, month: str | None = MONTH, reg: AgentRegistry = Depends(registry)):
            return run_tool(reg, "bo3", tool, lambda ag: getattr(ag, tool)(seller_id, month))
    return endpoint


_tool_route("profile", "get_seller_profile", "Profil d'activité (12 mois) et segment descriptif")
_tool_route("peers", "get_peer_group", "Référence et vendeurs à l'activité la plus proche (descriptif)")
_tool_route("comparison", "compare_to_peers", "Taux du vendeur vs référence (n, IC, entonnoir, observé / attendu)", with_metric=True)
_tool_route("deterioration", "detect_deterioration", "Alertes niveau / tendance, sévérité, persistance, alertes passées", with_metric=True)
_tool_route("strengths", "find_strengths", "Points forts (12 mois nettement sous la référence)")
_tool_route("orders", "get_seller_orders", "Commandes récentes dont un problème était connu à la décision")
_tool_route("voice", "seller_voice", "Aspects critiqués dans les avis des clients du vendeur")
_tool_route("multi-seller", "multi_seller_exposure", "Commandes multi-vendeurs (non attribuées)")
_tool_route("geography", "get_seller_geography", "Carte des clients du vendeur : États, régions, distance et retards par distance")
_tool_route("benchmark", "competitive_benchmark", "Positionnement concurrentiel : rang dans la catégorie et parmi les concurrents directs")


@router.get("/sellers/{seller_id}/voice/translations", summary="Traduction locale (portugais → français) des extraits d'avis affichés")
def voice_translations(seller_id: str = SELLER, month: str | None = MONTH, reg: AgentRegistry = Depends(registry)):
    """Sélection des extraits sous verrou (rapide), puis traduction HORS verrou : les autres requêtes BO3 ne sont pas bloquées.
    Les traductions sont mises en cache : les audits, l'assistant et l'analyse suivants les utilisent directement."""
    def pick():
        with reg.use("bo3") as ag:
            v = ag.seller_voice(seller_id, month)
            sid, M = ag._resolve(seller_id), ag._month(month)
            return v, dict(ag._quote_sources.get((sid, M), {})), ag._translator
    voice, sources, tr = _errors("bo3", pick)
    if tr is None:
        return {"available": False, "translations": {}}
    out = {}
    for q in voice.get("quotes") or []:
        if q.get("machine_translated"):
            out[q["review_id"]] = {"excerpt": q["excerpt"], "original": q.get("excerpt_original")}
            continue
        title, text = sources.get(q["review_id"], (None, None))
        fr = tr.review(title, text)
        if fr:
            out[q["review_id"]] = {"excerpt": (fr[:200] + "…") if len(fr) > 200 else fr, "original": q["excerpt"]}
    return {"available": not tr._unavailable, "translations": out}


@router.get("/sellers/{seller_id}/history", response_model=ToolResponse, summary="Évolution mensuelle jusqu'au mois de décision")
def history(seller_id: str = SELLER, month: str | None = MONTH, n_months: int = Query(6, ge=1, le=24), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo3", "get_seller_history", lambda ag: ag.get_seller_history(seller_id, month, n_months))


@router.post("/ask", response_model=AgentReportResponse, summary="Question libre (routage de BO3)")
def ask(body: AskRequest, reg: AgentRegistry = Depends(registry)):
    return run_report(reg, "bo3", lambda ag: ag.ask(body.question))
