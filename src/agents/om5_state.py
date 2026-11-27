"""Typed shared state for the OM5 LangGraph workflow."""
from __future__ import annotations

from typing import Any, TypedDict

from .core import Report


class OM5State(TypedDict, total=False):
    month: str
    mode: str
    include_agents: bool
    kpi_values: dict[str, Any] | None
    historical_comparisons: dict[str, Any] | None
    detected_anomalies: list[dict[str, Any]]
    active_business_signals: list[dict[str, Any]]
    segment_analysis: dict[str, Any]
    investigation_plan: list[dict[str, Any]]
    bo1_results: dict[str, Any] | None
    bo2_results: dict[str, Any] | None
    bo3_results: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    priority_scores: list[dict[str, Any]]
    deterministic_report: Report | None
    generated_report: dict[str, Any] | None
    final_report: Report | None
    validation_errors: list[str]
    retry_counter: int
    partial: bool
    generation_mode: str
    llm_provider: str | None
    llm_model: str | None
    llm_latency_ms: float | None
    validation_status: str
    fallback_used: bool
    fallback_reason: str | None
