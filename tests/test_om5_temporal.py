"""Temporal leakage invariance tests for OM5."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agents.core import DataStore  # noqa: E402
from agents.om5_kpis import monthly_kpis  # noqa: E402


@unittest.skipUnless((ROOT / "data/silver/orders_analysis.csv.gz").exists(), "données Olist préparées absentes")
class TestTemporalIntegrity(unittest.TestCase):
    def test_future_event_suppression_invariance(self):
        store = DataStore(ROOT)
        baseline = {x["metric_id"]: x["value"] for x in monthly_kpis(store, "2018-03", "as_of")}
        orders = store.orders.copy(deep=True)
        cutoff = pd.Timestamp("2018-04-01")
        for col in ("order_delivered_customer_date", "order_delivered_carrier_date", "review_answer_timestamp"):
            ts = pd.to_datetime(orders[col], errors="coerce")
            orders.loc[ts >= cutoff, col] = pd.NaT
        truncated = DataStore(ROOT); truncated._cache["orders"] = orders
        got = {x["metric_id"]: x["value"] for x in monthly_kpis(truncated, "2018-03", "as_of")}
        for metric in ("order_count", "late_rate", "poor_review_rate", "late_handover_rate", "average_review_score"):
            self.assertTrue((baseline[metric] is None and got[metric] is None) or np.isclose(baseline[metric], got[metric], equal_nan=True), metric)

    def test_asof_excludes_outcomes_observed_after_cutoff(self):
        store = DataStore(ROOT)
        asof = {x["metric_id"]: x for x in monthly_kpis(store, "2018-03", "as_of")}
        retro = {x["metric_id"]: x for x in monthly_kpis(store, "2018-03", "retrospective")}
        self.assertLess(asof["late_rate"]["denominator"], retro["late_rate"]["denominator"])
        self.assertLess(asof["poor_review_rate"]["denominator"], retro["poor_review_rate"]["denominator"])

