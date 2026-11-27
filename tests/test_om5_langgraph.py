"""LangGraph, provider-independent validation and fallback tests (no paid API calls)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.om5_agent import ReportingAgent  # noqa: E402
from agents.core import EvidenceLog  # noqa: E402
from agents.om5_validation import validate_generated_report  # noqa: E402


def structured(context, bad_ref: bool = False, bad_score: bool = False):
    ids = context["allowed_evidence_ids"]
    ref = "missing:evidence" if bad_ref else ids[0]
    recommendations = []
    for item in context["recommendation_slots"]:
        recommendations.append({"title": "Investigation ciblée", "description": "Vérifier le signal avec l'équipe métier.",
            "business_justification": "Le détecteur statistique justifie une revue humaine.", "related_anomaly": "none" if item["metric_id"] == "none" else item["metric_id"],
            "relevant_segment_or_seller": None, "priority_level": "haute", "priority_score": item["priority_score"] + (1 if bad_score else 0),
            "responsible_team": "Opérations", "timeframe": "Sous 7 jours", "expected_qualitative_benefit": "Diagnostic plus précis",
            "evidence_ids": item["evidence_ids"]})
    if not recommendations:
        recommendations = [{"title": "Maintenir la surveillance", "description": "Poursuivre la revue mensuelle.",
            "business_justification": "Aucune dégradation n'est signalée.", "related_anomaly": "none", "relevant_segment_or_seller": None,
            "priority_level": "basse", "priority_score": 0, "responsible_team": "Pilotage", "timeframe": "Mois prochain",
            "expected_qualitative_benefit": "Détection précoce", "evidence_ids": [ref]}]
    return {"period": context["period"], "temporal_mode": context["temporal_mode"],
            "executive_summary": {"text": "Synthèse fondée sur les preuves disponibles.",
                                  "evidence_ids": [ref] if bad_ref else ids[:2]},
            "insights": [], "recommendations": recommendations}


class FakeGenerator:
    provider = "groq"; model = "openai/gpt-oss-test"
    def __init__(self, sequence=None, error=None):
        self.sequence = list(sequence or []); self.error = error; self.calls = 0
    def generate(self, context, validation_errors=None):
        self.calls += 1
        if self.error:
            raise self.error
        choice = self.sequence[min(self.calls - 1, len(self.sequence) - 1)] if self.sequence else "valid"
        return structured(context, bad_ref=choice == "bad_ref", bad_score=choice == "bad_score"), 12.5


class TestGeneratedValidation(unittest.TestCase):
    def test_numerical_inconsistency_rejected(self):
        log = EvidenceLog(); evidence_id = "om5:kpi:as_of:2018-03:order_count"
        log.add(evidence_id, "fait", "gold", {"value": 10, "period": "2018-03"})
        payload = {"period": "2018-03", "temporal_mode": "as_of",
            "executive_summary": {"text": "777 commandes observées.", "evidence_ids": [evidence_id]}, "insights": [],
            "recommendations": [{"title": "Suivre", "related_anomaly": "none", "priority_score": 0, "evidence_ids": [evidence_id]}]}
        ok, problems = validate_generated_report(payload, log, "2018-03", "as_of", {}, [], set())
        self.assertFalse(ok); self.assertTrue(any("numérique" in x for x in problems))


@unittest.skipUnless((ROOT / "data/silver/orders_analysis.csv.gz").exists(), "données Olist absentes")
class TestLangGraphOM5(unittest.TestCase):
    def test_compiled_graph_and_no_anomaly_route(self):
        agent = ReportingAgent(ROOT)
        report = agent.run("2017-07", "as_of", False)
        nodes = [x["tool"] for x in report.meta["tool_trace"] if x.get("kind") == "node"]
        self.assertEqual(report.meta["graph_engine"], "langgraph")
        self.assertNotIn("segment_analysis", nodes); self.assertIn("consolidation", nodes)
        self.assertTrue(report.meta["fallback_used"])

    def test_single_and_multiple_anomaly_routing(self):
        single = ReportingAgent(ROOT).run("2017-06", "as_of", False)
        self.assertIn("segment_analysis", [x["tool"] for x in single.meta["tool_trace"]])
        called = []
        def collaborator(name, method, kwargs):
            called.append(name); return {"agent": name}, []
        multi = ReportingAgent(ROOT, collaborator=collaborator).run("2018-03", "as_of", True)
        self.assertEqual(called, ["bo1", "bo2", "bo3"])
        self.assertEqual(set(multi.meta["agent_insights"]), {"bo1", "bo2", "bo3"})

    def test_valid_structured_generation(self):
        generator = FakeGenerator()
        report = ReportingAgent(ROOT, report_generator=generator).run("2018-03", "as_of", False)
        self.assertEqual(report.meta["generation_mode"], "groq")
        self.assertEqual(report.meta["validation_status"], "valid")
        self.assertFalse(report.meta["fallback_used"]); self.assertEqual(generator.calls, 1)

    def test_invalid_evidence_and_score_bounded_regeneration(self):
        generator = FakeGenerator(["bad_ref", "valid"])
        report = ReportingAgent(ROOT, report_generator=generator).run("2018-03", "as_of", False)
        self.assertEqual(generator.calls, 2); self.assertEqual(report.meta["validation_status"], "valid")
        always_bad = FakeGenerator(["bad_score"])
        fallback = ReportingAgent(ROOT, report_generator=always_bad).run("2018-03", "as_of", False)
        self.assertEqual(always_bad.calls, 2); self.assertTrue(fallback.meta["fallback_used"])
        self.assertEqual(fallback.meta["generation_mode"], "deterministic")

    def test_timeout_or_quota_error_falls_back(self):
        generator = FakeGenerator(error=TimeoutError("quota or timeout"))
        report = ReportingAgent(ROOT, report_generator=generator).run("2018-03", "as_of", False)
        self.assertTrue(report.meta["fallback_used"]); self.assertIn("TimeoutError", report.meta["fallback_reason"])
        self.assertEqual(generator.calls, 2)
