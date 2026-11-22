"""Schémas de réponse. Le rapport reprend EXACTEMENT le contrat `Report.to_dict()` des agents (BO1 / BO2 inchangés)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Month = Field(None, pattern=r"^20\d{2}-\d{2}$", description="Mois de décision AAAA-MM (décision à la fin du mois)")


class LineOut(BaseModel):
    text: str
    evidence: list[str] = []


class ReportOut(BaseModel):
    title: str
    narrative: str = ""
    narrative_source: str = "deterministe"
    facts: list[LineOut] = []
    estimates: list[LineOut] = []
    similar_experiences: list[LineOut] = []
    actions: list[LineOut] = []
    caveats: list[str] = []
    meta: dict[str, Any] = {}
    section_titles: dict[str, str] | None = None


class EvidenceOut(BaseModel):
    id: str
    kind: str = Field(description="fait | estimation | experience_autres_clients")
    source: str
    payload: Any


class AgentReportResponse(BaseModel):
    agent: Literal["bo1", "bo2", "bo3"]
    report: ReportOut
    markdown: str
    evidence: list[EvidenceOut]


class ToolResponse(BaseModel):
    agent: Literal["bo1", "bo2", "bo3"]
    tool: str
    result: Any
    evidence: list[EvidenceOut]


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class AgentStatus(BaseModel):
    state: str
    load_seconds: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    agents: dict[str, AgentStatus]
    config: dict[str, Any]


class ErrorResponse(BaseModel):
    detail: str
