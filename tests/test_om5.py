"""Unit and workflow tests for OM5 on the authentic local Olist preparation."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.core import DataStore, EvidenceLog, Line, Report  # noqa: E402
from agents.om5_agent import ReportingAgent  # noqa: E402
from agents.om5_anomalies import compare_values, detect_anomalies, robust_z  # noqa: E402
from agents.om5_kpis import monthly_kpis, trend_frame  # noqa: E402
from agents.om5_validation import validate_report  # noqa: E402


@unittest.skipUnless((ROOT / "data/silver/orders_analysis.csv.gz").exists(), "données Olist préparées absentes")
class TestKpis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = DataStore(ROOT)

    def test_retrospective_matches_gold(self):
        got = {x["metric_id"]: x for x in monthly_kpis(self.store, "2018-03", "retrospective")}
        row = self.store.monthly.loc[self.store.monthly.purchase_month.eq("2018-03")].iloc[0]
        for metric in ("order_count", "late_rate", "poor_review_rate", "average_review_score", "item_price_total"):
            self.assertTrue(np.isclose(got[metric]["value"], row[metric]))

    def test_zero_denominator_and_incomplete_month(self):
        got = {x["metric_id"]: x for x in monthly_kpis(self.store, "2016-11", "as_of")}
        self.assertIsNone(got["late_rate"]["value"])
        self.assertIsNone(got["poor_review_rate"]["value"])
        self.assertEqual(got["order_count"]["quality_status"], "no_orders")

    def test_metadata_and_denominators(self):
        got = {x["metric_id"]: x for x in monthly_kpis(self.store, "2018-03", "as_of")}
        late = got["late_rate"]
        self.assertEqual(late["value"], late["numerator"] / late["denominator"])
        self.assertEqual(late["mode"], "as_of")
        self.assertIn("orders_analysis", late["source"])
        self.assertTrue(late["evidence_id"].startswith("om5:kpi:"))
        self.assertGreater(got["active_seller_count"]["value"], got["alerted_seller_count"]["value"])
        self.assertGreater(got["evaluable_seller_count"]["value"], 0)


class TestStatistics(unittest.TestCase):
    def test_comparisons(self):
        self.assertEqual(compare_values(.2, .1, True)["percentage_point_change"], 10.0)
        self.assertIsNone(compare_values(2, 0)["relative_change_pct"])
        self.assertIsNone(compare_values(None, 1)["absolute_change"])

    def test_robust_z_small_history_and_outlier(self):
        self.assertIsNone(robust_z(pd.Series([1, 2, 3]), 10))
        self.assertGreater(robust_z(pd.Series([1, 1.1, .9, 1, 1.05, .95]), 3), 3.5)

    @unittest.skipUnless((ROOT / "data/gold/monthly_business_kpis.csv").exists(), "données Olist absentes")
    def test_real_anomaly_has_explicit_n(self):
        rows = detect_anomalies(trend_frame(DataStore(ROOT), "as_of"), "2018-03")
        late = next(x for x in rows if x["metric_id"] == "late_rate")
        self.assertTrue(late["anomaly"])
        self.assertGreater(late["sample_size"], 30)
        self.assertIsNotNone(late["q_value"])


@unittest.skipUnless((ROOT / "data/silver/orders_analysis.csv.gz").exists(), "données Olist préparées absentes")
class TestWorkflow(unittest.TestCase):
    def test_dynamic_plan_no_llm_and_valid_evidence(self):
        agent = ReportingAgent(ROOT)
        report = agent.run("2018-03", "as_of", include_agents=False)
        tools = [x["tool"] for x in report.meta["tool_trace"]]
        self.assertIn("analyze_segments", tools)
        self.assertFalse(any(x.startswith("collect_") for x in tools))
        self.assertTrue(report.meta["evidence_valid"])
        self.assertLessEqual(report.meta["calls_used"], report.meta["call_budget"])
        review_segments = agent.analyze_segments("2018-03", "average_review_score", "as_of")
        self.assertTrue(all(1 <= x["value"] <= 5 for x in review_segments["segments"]["state"]))

    def test_unavailable_agents_produce_partial_report(self):
        def broken(name, method, kwargs):
            raise RuntimeError("indisponible")
        report = ReportingAgent(ROOT, collaborator=broken).run("2018-03", "as_of", include_agents=True)
        self.assertTrue(report.meta["partial"])
        self.assertTrue(report.meta["evidence_valid"])
        self.assertEqual(sum(x["status"] == "error" for x in report.meta["tool_trace"]), 3)

    def test_evidence_validator_rejects_wrong_reference_and_causality(self):
        log = EvidenceLog(); log.add("om5:x", "fait", "x", {"value": 1})
        report = Report("x", facts=[Line("Ce signal cause le retard.", ["missing"])])
        ok, problems = validate_report(report, log)
        self.assertFalse(ok)
        self.assertTrue(any("preuve inconnue" in x for x in problems))
        self.assertTrue(any("causalité" in x for x in problems))

