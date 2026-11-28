"""BO2 — voix du client. Enveloppes fines des méthodes publiques, plus /overview pour les graphiques."""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, Query

from ..registry import AgentRegistry
from ..schemas import AgentReportResponse, AskRequest
from ..insights import bo2_overview
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


@router.get("/overview", summary="Données des graphiques de la page BO2 (aspects, référence, évolution)")
def overview(month: str | None = Query(None, pattern=r"^20\d{2}-\d{2}$"), state: str | None = Query(None, pattern=r"^[A-Z]{2}$"),
             category: str | None = None, reg: AgentRegistry = Depends(registry)):
    def go():
        with reg.use("bo2") as ag:
            return bo2_overview(ag, month, state, category)
    return _errors("bo2", go)


# ----------------------------------------------------------------------------- assistant de la page « Voix du client »
from pydantic import BaseModel, Field  # noqa: E402

from agents.core import EvidenceLog  # noqa: E402

from ..serialization import evidence_snapshot  # noqa: E402

BO2_FOLLOW = ["Quelles plaintes augmentent ce mois-ci ?", "De quoi se plaignent le plus les clients ?",
              "Montre-moi des avis sur la livraison", "Que faut-il faire en priorité ?", "Qu'apprécient les clients ?"]


class Bo2ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    month: str | None = Field(None, pattern=r"^20\d{2}-\d{2}$")
    state: str | None = Field(None, pattern=r"^[A-Z]{2}$")
    category: str | None = None


def _fold(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


@router.post("/chat", summary="Assistant de la page Voix du client : répond à partir du rapport BO2, phrase par phrase avec ses preuves")
def bo2_chat(body: Bo2ChatRequest, reg: AgentRegistry = Depends(registry)):
    """Réponse déterministe (aucun LLM) : la question est routée par BO2 (mois, État, catégorie, aspect, intention),
    puis on garde du rapport BO2 les lignes qui répondent à la question. Chaque phrase cite ses preuves."""
    def go():
        with reg.use("bo2") as ag:
            ag.log = EvidenceLog()
            p = ag._parse(body.question)
            month = p["month"] or body.month or ag.default_month()
            state = p["state"] or body.state
            category = p["category"] or body.category
            q = _fold(body.question)
            positive = p["intent"] == "positif"
            rep = ag.report(month, state, category, focus=p["aspect"], sentiment_focus="positif" if positive else "negatif", use_llm=False)
            facts = [{"texte": x.text, "type": "fait", "preuves": x.evidence} for x in rep.facts]
            est = [x for x in rep.estimates]
            alerts = [{"texte": x.text.replace("ALERTE plainte émergente", "Plainte en hausse"), "type": "hypothese", "preuves": x.evidence}
                      for x in est if x.text.startswith("ALERTE")]
            terms = [{"texte": x.text, "type": "piste", "preuves": x.evidence} for x in est if x.text.startswith("Termes")]
            crit = [{"texte": x.text, "type": "hypothese", "preuves": x.evidence} for x in est if x.text.startswith("Critiqué")]
            liked = [{"texte": x.text, "type": "hypothese", "preuves": x.evidence} for x in est if x.text.startswith("Apprécié")]
            quotes = [{"texte": x.text, "type": "fait", "preuves": x.evidence} for x in rep.similar]
            actions = [{"texte": x.text, "type": "piste", "preuves": x.evidence} for x in rep.actions]
            if re.search(r"augment|hausse|alerte|nouve|emerg|apparu", q):
                items = (alerts or [{"texte": f"Aucune plainte n'augmente anormalement en {month} par rapport aux 12 mois précédents.", "type": "fait",
                                     "preuves": [e for e in [f"mdl:emerging:{month}"] if e in ag.log.ids()]}]) + terms[:1]
            elif re.search(r"avis|exemple|montre|extrait|disent|citation", q):
                items = quotes[:4]
            elif re.search(r"faire|action|prior|recommand|que doit", q):
                items = actions[:4]
            elif positive:
                items = liked[:3] + quotes[:2]
            else:
                items = facts[1:2] + crit[:3] + alerts[:2]
            items = [it for it in items if it["texte"]]
            if not items:
                items = [{"texte": "Je ne trouve pas d'élément suffisamment étayé pour cette question dans les avis de ce périmètre.", "type": "inconnu", "preuves": []}]
            cited = {c for it in items for c in it["preuves"]}
            scope = " · ".join(x for x in [month, state, category] if x)
            return {"model": "bo2", "mode": "sans_ia", "items": items, "questions": [], "rejected": [],
                    "follow_up": [f for f in BO2_FOLLOW if _fold(f) != q][:3],
                    "evidence": [e for e in evidence_snapshot(ag.log) if e["id"] in cited],
                    "notice": f"Réponse de l'agent BO2 (voix du client) sur {scope}, construite directement à partir des avis analysés.",
                    "month": month}
    return _errors("bo2", go)
