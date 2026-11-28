"""BO4 customer assistant endpoints."""
from __future__ import annotations
from fastapi import APIRouter, Depends, Query, Request
from ..llm.bo4 import converse
from ..registry import AgentRegistry
from ..schemas import BO4AskRequest, BO4ChatResponse, ToolResponse
from ..serialization import evidence_snapshot, jsonable
from .common import _errors, registry, run_tool
from .llm import provider_for
from ..llm.local import LocalHermesProvider
import re
import threading
import time
from pydantic import BaseModel, Field
from agents.bo4_agent import _norm

class ConversationRequest(BaseModel):
    session_id: str = Field(pattern=r"^[a-fA-F0-9-]{36}$")
    question: str = Field(min_length=1, max_length=2000)

_sessions: dict = {}
_session_lock = threading.RLock()
_months = {name: i + 1 for i, name in enumerate("janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre".split())}


def customer_provider(request: Request, slot: str = "a"):
    settings = request.app.state.settings
    if settings.bo4_local_model:
        return LocalHermesProvider(settings.bo4_local_model), "Ollama local"
    configured = settings.llm_model_a if slot == "a" else settings.llm_model_b
    if settings.openrouter_api_key and configured:
        return provider_for(request, slot), "OpenRouter"
    return None, "indisponible"

router = APIRouter(prefix="/api/bo4", tags=["BO4 - Assistant client"])

@router.post("/conversation")
def conversation(body: ConversationRequest, request: Request, reg: AgentRegistry = Depends(registry)):
    def go():
        with _session_lock, reg.use("bo4") as agent:
            now = time.monotonic()
            for key in list(_sessions):
                if now - _sessions[key]["touched"] > 3600: del _sessions[key]
            if len(_sessions) >= 1000 and body.session_id not in _sessions:
                del _sessions[min(_sessions, key=lambda key: _sessions[key]["touched"])]
            state = _sessions.setdefault(body.session_id, {"order": None, "date": None, "history": [], "touched": now})
            state["touched"] = now
            q = _norm(body.question)
            ids = re.findall(r"\b[a-f0-9]{32}\b", q)
            if len(set(ids)) > 1: return {"answer": "Quelle commande souhaitez-vous consulter en premier ?", "limited": False}
            candidate = ids[0] if ids else state["order"]
            if candidate:
                try: agent._order(candidate)
                except KeyError: return {"answer": "Je ne retrouve pas cette commande. Pouvez-vous vérifier sa référence ?", "limited": False}
            date = None
            match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", q)
            if match: date = match.group(0)
            else:
                match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", q)
                if match: date = f"{match[3]}-{int(match[2]):02d}-{int(match[1]):02d}"
                else:
                    match = re.search(r"\b(\d{1,2})(?:er)? (" + "|".join(_months) + r") (20\d{2})\b", q)
                    if match: date = f"{match[3]}-{_months[match[2]]:02d}-{int(match[1]):02d}"
            changed_order = candidate != state["order"]
            resolved_date = date or (None if changed_order and state["order"] else state["date"])
            if date:
                import datetime
                try: datetime.date.fromisoformat(date)
                except ValueError: return {"answer": "Cette date n’est pas valide. Quelle date historique souhaitez-vous utiliser ?", "limited": False}
            if changed_order or (date and date != state["date"]): state["history"] = []
            state["order"], state["date"] = candidate, resolved_date
            if not candidate: return {"answer": "Pouvez-vous me transmettre votre numéro de commande ?", "limited": False}
            if not resolved_date: return {"answer": "À quelle date historique souhaitez-vous consulter cette commande ? Par exemple : le 10 juillet 2018.", "limited": False}
            try: as_of = agent.resolve_as_of(candidate, resolved_date + "T23:59:59")
            except ValueError: return {"answer": "Cette date précède la création de votre commande. Pouvez-vous choisir une date ultérieure ?", "limited": False}
            provider, provider_name = customer_provider(request)
            result = converse(agent, provider, candidate, body.question, as_of, state["history"], provider_name=provider_name)
            state["history"] = [*state["history"], {"role": "user", "content": body.question}, {"role": "assistant", "content": result["text"]}][-12:]
            return {"answer": result["text"], "limited": result["source"] == "deterministic_fallback",
                    "answer_source": result["source"], "provider": result["debug"].get("provider"),
                    "model": result["debug"].get("model")}
    return _errors("bo4", go)

@router.get("/orders/{order_id}/context", response_model=ToolResponse)
def context(order_id: str, as_of: str | None = Query(None), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo4", "get_order_context", lambda a: a.get_delivery_context(order_id, as_of))

@router.get("/orders/{order_id}/eta", response_model=ToolResponse)
def eta(order_id: str, as_of: str | None = Query(None), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo4", "predict_delivery_interval", lambda a: a.predict_delivery_interval(order_id, as_of))

@router.get("/orders/{order_id}/similar", response_model=ToolResponse)
def similar(order_id: str, as_of: str | None = Query(None), k: int = Query(5, ge=1, le=20), reg: AgentRegistry = Depends(registry)):
    return run_tool(reg, "bo4", "find_similar_orders", lambda a: a.find_similar_orders(order_id, as_of, k))

@router.post("/ask", response_model=BO4ChatResponse)
def ask(body: BO4AskRequest, request: Request, reg: AgentRegistry = Depends(registry)):
    """Conversational BO4 endpoint: LLM tool selection with validated deterministic fallback."""
    provider, provider_name = customer_provider(request, body.model)

    def go():
        with reg.use("bo4") as agent:
            as_of = agent.resolve_as_of(body.order_id, body.as_of)
            result = converse(agent, provider, body.order_id, body.question, as_of,
                              [turn.model_dump() for turn in body.history], provider_name=provider_name)
            report = result["report"]
            return {"agent": "bo4", "answer": result["text"], "answer_source": result["source"],
                    "language": result["language"], "report": jsonable(report.to_dict()),
                    "markdown": report.to_markdown(), "evidence": evidence_snapshot(agent.log),
                    "debug": jsonable(result["debug"])}
    return _errors("bo4", go)
