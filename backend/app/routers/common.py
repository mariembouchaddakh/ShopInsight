"""Exécution d'un appel d'agent sous verrou et mise en forme de la réponse (aucune logique métier)."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import HTTPException, Request

from ..registry import AgentRegistry, AgentUnavailable
from ..serialization import evidence_snapshot, jsonable

import sys
from ..config import ROOT

sys.path.insert(0, str(ROOT / "src"))
from agents.core import EvidenceLog  # noqa: E402


def registry(request: Request) -> AgentRegistry:
    return request.app.state.registry


def _errors(name: str, fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except AgentUnavailable as e:
        raise HTTPException(status_code=503, detail=f"Agent {name} indisponible : {e}") from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=503, detail=f"Données manquantes : {e}") from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e.args[0]) if e.args else "introuvable") from e
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e


def run_report(reg: AgentRegistry, name: str, call: Callable[[Any], Any]) -> dict:
    """Appelle une méthode publique qui renvoie un `Report` ; renvoie le contrat `to_dict()` tel quel + Markdown + preuves."""
    def go() -> dict:
        with reg.use(name) as ag:
            rep = call(ag)
            return {"agent": name, "report": jsonable(rep.to_dict()), "markdown": rep.to_markdown(), "evidence": evidence_snapshot(ag.log)}
    return _errors(name, go)


def run_tool(reg: AgentRegistry, name: str, tool: str, call: Callable[[Any], Any]) -> dict:
    """Appelle un outil BO3 avec un journal de preuves neuf ; renvoie le résultat et ses preuves."""
    def go() -> dict:
        with reg.use(name) as ag:
            ag.log = EvidenceLog()
            res = call(ag)
            return {"agent": name, "tool": tool, "result": jsonable(res), "evidence": evidence_snapshot(ag.log)}
    return _errors(name, go)
