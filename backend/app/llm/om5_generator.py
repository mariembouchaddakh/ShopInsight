"""Provider-independent structured generation adapters for OM5."""
from __future__ import annotations

import os
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .om5_prompts import build_prompt

Section = Literal["health", "kpi", "comparison", "anomaly", "statistics", "segments", "agents", "impact", "limitations"]


class StrictModel(BaseModel):
    """JSON Schema base compatible with Groq strict structured outputs."""
    model_config = ConfigDict(extra="forbid")


class GroundedClaim(StrictModel):
    section: Section
    text: str = Field(description="One concise French sentence, without embedding evidence IDs in the text")
    evidence_ids: list[str] = Field(description="One or more exact IDs copied from allowed_evidence_ids")


class ExecutiveSummary(StrictModel):
    text: str = Field(description="Concise French executive summary, maximum 70 words")
    evidence_ids: list[str] = Field(description="Two to five exact IDs copied from allowed_evidence_ids")


class GeneratedRecommendation(StrictModel):
    metric_id: str = Field(description="Exact metric_id copied from one recommendation_slot")
    title: str
    description: str
    business_justification: str
    relevant_segment_or_seller: str | None
    priority_level: Literal["haute", "moyenne", "basse"]
    responsible_team: str
    timeframe: str
    expected_qualitative_benefit: str
    evidence_ids: list[str] = Field(description="Exact IDs from the matching recommendation_slot and analytical context")


class GeneratedOM5Report(StrictModel):
    period: str
    temporal_mode: Literal["as_of", "retrospective"]
    executive_summary: ExecutiveSummary
    insights: list[GroundedClaim] = Field(description="At most one claim per relevant section")
    recommendations: list[GeneratedRecommendation] = Field(description="Exactly one recommendation per recommendation_slot")


def _enrich(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Restore immutable deterministic scores after LLM generation."""
    slots = {x["metric_id"]: x for x in context.get("recommendation_slots", [])}
    enriched = []
    for original in payload.get("recommendations", []):
        item = dict(original)
        metric = item.pop("metric_id", "")
        slot = slots.get(metric)
        item["related_anomaly"] = "none" if metric == "none" else metric
        item["priority_score"] = slot["priority_score"] if slot is not None else None
        enriched.append(item)
    payload["recommendations"] = enriched
    return payload


class GroqOM5Generator:
    """Official Groq SDK adapter using strict JSON Schema constrained decoding."""
    provider = "groq"

    def __init__(self, api_key: str, model: str = "openai/gpt-oss-120b", timeout_seconds: float = 90.0,
                 network_retries: int = 1, max_completion_tokens: int = 2_200) -> None:
        from groq import Groq
        self.model = model
        self._max_completion_tokens = max_completion_tokens
        self._client = Groq(api_key=api_key, timeout=timeout_seconds, max_retries=max(0, min(network_retries, 2)))

    def generate(self, context: dict[str, Any], validation_errors: list[str] | None = None) -> tuple[dict[str, Any], float]:
        from groq import BadRequestError

        started = time.perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Tu es le rédacteur BI de ShopInsight. Retourne uniquement la structure JSON demandée."},
                    {"role": "user", "content": build_prompt(context, validation_errors)},
                ],
                temperature=0.0,
                max_completion_tokens=self._max_completion_tokens,
                reasoning_effort="low",
                response_format={"type": "json_schema", "json_schema": {
                    "name": "om5_marketplace_report", "strict": True,
                    "schema": GeneratedOM5Report.model_json_schema(),
                }},
            )
        except BadRequestError as exc:
            body = exc.body if isinstance(exc.body, dict) else {}
            error = body.get("error", body) if isinstance(body, dict) else {}
            message = error.get("message", str(exc)) if isinstance(error, dict) else str(exc)
            raise RuntimeError(f"Groq structured output rejected: {message}") from exc
        content = response.choices[0].message.content or ""
        parsed = GeneratedOM5Report.model_validate_json(content).model_dump()
        return _enrich(parsed, context), round(1000 * (time.perf_counter() - started), 1)


class GeminiOM5Generator:
    """Optional backwards-compatible Google Gemini adapter."""
    provider = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", timeout_ms: int = 60_000,
                 network_retries: int = 1) -> None:
        from google import genai
        from google.genai import types
        self.model = model
        self._types = types
        self._network_retries = max(0, min(network_retries, 2))
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=timeout_ms))

    def generate(self, context: dict[str, Any], validation_errors: list[str] | None = None) -> tuple[dict[str, Any], float]:
        started = time.perf_counter()
        last_error: Exception | None = None
        for attempt in range(self._network_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=build_prompt(context, validation_errors),
                    config=self._types.GenerateContentConfig(
                        temperature=0.0, max_output_tokens=3000,
                        thinking_config=self._types.ThinkingConfig(thinking_budget=0),
                        response_mime_type="application/json",
                        response_json_schema=GeneratedOM5Report.model_json_schema(),
                    ),
                )
                parsed = GeneratedOM5Report.model_validate_json(response.text or "").model_dump()
                return _enrich(parsed, context), round(1000 * (time.perf_counter() - started), 1)
            except Exception as exc:
                last_error = exc
                transient = isinstance(exc, TimeoutError) or any(code in str(exc).upper() for code in ("429", "503", "504", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "DEADLINE_EXCEEDED"))
                if not transient or attempt >= self._network_retries:
                    raise
                time.sleep(1.0 + attempt)
        raise last_error or RuntimeError("Gemini indisponible")


def create_generator(provider: str, *, groq_api_key: str | None = None, groq_model: str = "openai/gpt-oss-120b",
                     gemini_api_key: str | None = None, gemini_model: str = "gemini-2.5-flash"):
    selected = provider.strip().lower()
    if selected == "groq":
        return GroqOM5Generator(groq_api_key, groq_model) if groq_api_key else None
    if selected in {"gemini", "google-gemini"}:
        return GeminiOM5Generator(gemini_api_key, gemini_model) if gemini_api_key else None
    raise ValueError(f"Fournisseur OM5 LLM non supporté : {provider}")


def generator_from_env(env: dict[str, str] | None = None):
    values = env or os.environ
    if values.get("OM5_LLM_ENABLED", "false").lower() not in {"1", "true", "yes"}:
        return None
    return create_generator(
        values.get("OM5_LLM_PROVIDER", "groq"),
        groq_api_key=values.get("GROQ_API_KEY", "").strip() or None,
        groq_model=values.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        gemini_api_key=values.get("GEMINI_API_KEY", "").strip() or None,
        gemini_model=values.get("GEMINI_MODEL", "gemini-2.5-flash"),
    )


__all__ = ["GeneratedOM5Report", "GeminiOM5Generator", "GroqOM5Generator", "create_generator", "generator_from_env"]
