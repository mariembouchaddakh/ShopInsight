"""Gemini Flash structured generation adapter for OM5."""
from __future__ import annotations

import os
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from .om5_prompts import build_prompt


class GroundedClaim(BaseModel):
    text: str
    evidence_ids: list[str]


class Recommendation(BaseModel):
    title: str
    description: str
    business_justification: str
    related_anomaly: str = Field(description="Exact metric_id from priority_scores, or 'none' when priority_scores is empty")
    relevant_segment_or_seller: str | None = None
    priority_level: Literal["haute", "moyenne", "basse"]
    priority_score: float = Field(description="Exact deterministic priority_score from context; 0 only when related_anomaly is none")
    responsible_team: str
    timeframe: str
    expected_qualitative_benefit: str
    evidence_ids: list[str]


class ReportSections(BaseModel):
    marketplace_health: list[GroundedClaim]
    key_performance_indicators: list[GroundedClaim]
    performance_comparisons: list[GroundedClaim]
    anomalies_and_severity: list[GroundedClaim]
    statistical_interpretation: list[GroundedClaim]
    geographic_and_category_insights: list[GroundedClaim]
    multi_agent_findings: list[GroundedClaim]
    business_impact: list[GroundedClaim]
    data_quality_and_limitations: list[GroundedClaim]


class GeneratedOM5Report(BaseModel):
    period: str
    temporal_mode: Literal["as_of", "retrospective"]
    executive_summary: str
    executive_summary_evidence_ids: list[str]
    sections: ReportSections
    recommendations: list[Recommendation]


class GeminiOM5Generator:
    provider = "google-gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", timeout_ms: int = 45_000) -> None:
        from google import genai
        from google.genai import types
        self.model = model
        self._types = types
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))

    def generate(self, context: dict[str, Any], validation_errors: list[str] | None = None) -> tuple[dict[str, Any], float]:
        t0 = time.perf_counter()
        response = self._client.models.generate_content(
            model=self.model,
            contents=build_prompt(context, validation_errors),
            config=self._types.GenerateContentConfig(temperature=0.1, max_output_tokens=5000,
                thinking_config=self._types.ThinkingConfig(thinking_budget=0), response_mime_type="application/json",
                response_json_schema=GeneratedOM5Report.model_json_schema()),
        )
        parsed = GeneratedOM5Report.model_validate_json(response.text or "")
        return parsed.model_dump(), round(1000 * (time.perf_counter() - t0), 1)


def generator_from_env(env: dict[str, str] | None = None) -> GeminiOM5Generator | None:
    values = env or os.environ
    enabled = values.get("OM5_LLM_ENABLED", "false").lower() in {"1", "true", "yes"}
    key = values.get("GEMINI_API_KEY", "").strip()
    if not enabled or not key:
        return None
    return GeminiOM5Generator(key, values.get("GEMINI_MODEL", "gemini-2.5-flash"))


__all__ = ["GeneratedOM5Report", "GeminiOM5Generator", "generator_from_env"]
