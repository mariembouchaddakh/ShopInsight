"""Registre des agents : chaque agent est créé UNE fois via sa classe publique existante, puis réutilisé.

Les agents gardent un état par appel (journal de preuves `log`, caches) : chaque appel est donc sérialisé par un verrou propre à l'agent.
Le préchargement (BO3, puis BO1, puis BO2) tourne en arrière-plan au démarrage ; `/api/health` indique l'état de chaque agent.
Aucune logique métier ici : BO1 et BO2 sont appelés tels quels.
"""
from __future__ import annotations

import sys
import threading
import time
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from .config import ROOT, Settings

sys.path.insert(0, str(ROOT / "src"))
from agents.bo1_agent import PreventiveDiagnosisAgent  # noqa: E402
from agents.bo2_agent import VoiceOfCustomerAgent  # noqa: E402
from agents.bo3_agent import SellerAuditAgent  # noqa: E402
from agents.core import EvidenceLog, Report  # noqa: E402
from agents.om5_agent import ReportingAgent  # noqa: E402
from .llm.om5_generator import create_generator

FACTORIES: dict[str, Callable[[Path], Any]] = {
    "bo3": lambda p: SellerAuditAgent(p, translate_quotes=True),
    "bo1": lambda p: PreventiveDiagnosisAgent(p),
    "bo2": lambda p: VoiceOfCustomerAgent(p),
    "om5": lambda p: ReportingAgent(p),
}
WARMUP_ORDER = ("bo3", "bo1", "bo2", "om5")


class AgentUnavailable(RuntimeError):
    pass


class AgentRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._agents: dict[str, Any] = {}
        self._create_locks = {k: threading.Lock() for k in FACTORIES}
        self._call_locks = {k: threading.Lock() for k in FACTORIES}
        self.status: dict[str, dict] = {k: {"state": "not_loaded"} for k in FACTORIES}

    def _create(self, name: str) -> Any:
        with self._create_locks[name]:
            if name in self._agents:
                return self._agents[name]
            self.status[name] = {"state": "loading"}
            t0 = time.time()
            try:
                if name == "om5":
                    generator = create_generator(
                        self.settings.om5_llm_provider,
                        groq_api_key=self.settings.groq_api_key,
                        groq_model=self.settings.groq_model,
                        gemini_api_key=self.settings.gemini_api_key,
                        gemini_model=self.settings.gemini_model,
                    ) if self.settings.om5_llm_enabled else None
                    agent = ReportingAgent(self.settings.project_dir, report_generator=generator)
                else:
                    agent = FACTORIES[name](self.settings.project_dir)
                if name == "om5":
                    agent.collaborator = self.call_public
                if name == "bo2":
                    _ = agent.an  # analyse des avis (≈ 15 s) faite une fois
                if name == "bo3":
                    agent.warm()  # analyse des avis pour seller_voice + calculs du mois par défaut
            except FileNotFoundError as e:
                self.status[name] = {"state": "error", "error": f"données manquantes : {e}"}
                raise AgentUnavailable(self.status[name]["error"]) from e
            except Exception as e:  # noqa: BLE001
                self.status[name] = {"state": "error", "error": f"{type(e).__name__}: {e}"}
                raise AgentUnavailable(self.status[name]["error"]) from e
            self._agents[name] = agent
            self.status[name] = {"state": "ready", "load_seconds": round(time.time() - t0, 1)}
            return agent

    @contextmanager
    def use(self, name: str):
        """Fournit l'agent (créé au besoin) sous son verrou."""
        agent = self._agents.get(name) or self._create(name)
        with self._call_locks[name]:
            yield agent

    def call_public(self, name: str, method: str, kwargs: dict) -> tuple[Any, list]:
        """Call one collaborator and snapshot its evidence before releasing its lock."""
        if name == "om5" or name not in FACTORIES:
            raise AgentUnavailable(f"collaborateur inconnu : {name}")
        with self.use(name) as agent:
            fn = getattr(agent, method, None)
            if fn is None or method.startswith("_"):
                raise AgentUnavailable(f"méthode publique indisponible : {name}.{method}")
            result = fn(**kwargs)
            if isinstance(result, Report):
                result = result.to_dict()
            evidence = deepcopy(agent.log.with_prefix("")) if isinstance(getattr(agent, "log", None), EvidenceLog) else []
            return result, evidence

    def warmup(self) -> None:
        def run() -> None:
            for name in WARMUP_ORDER:
                try:
                    self._create(name)
                except AgentUnavailable:
                    continue
        threading.Thread(target=run, name="agents-warmup", daemon=True).start()
