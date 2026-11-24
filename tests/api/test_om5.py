"""API contract and export tests for OM5."""
from __future__ import annotations

import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("SHOPINSIGHT_WARMUP", "0")


@unittest.skipUnless((ROOT / "data/silver/orders_analysis.csv.gz").exists(), "données Olist préparées absentes")
class TestOm5Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.cm = TestClient(app); cls.client = cls.cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.cm.__exit__(None, None, None)

    def test_openapi_and_meta(self):
        paths = self.client.get("/openapi.json").json()["paths"]
        self.assertIn("/api/om5/report", paths)
        meta = self.client.get("/api/om5/meta").json()
        self.assertIn("as_of", meta["modes"])
        self.assertEqual(meta["historical_dataset"], "Olist 2016–2018")

    def test_kpis_and_invalid_period(self):
        res = self.client.get("/api/om5/kpis", params={"month": "2018-03", "mode": "as_of"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(all("evidence_id" in x for x in res.json()["kpis"]))
        self.assertEqual(self.client.get("/api/om5/kpis", params={"month": "2099-01"}).status_code, 422)
        self.assertEqual(self.client.get("/api/om5/kpis", params={"month": "2018-03", "mode": "future"}).status_code, 422)

    def test_report_without_external_agents(self):
        res = self.client.get("/api/om5/report", params={"month": "2018-03", "mode": "as_of", "include_agents": "false"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["report"]["meta"]["evidence_valid"])
        self.assertEqual(body["agent"], "om5")

    def test_exports(self):
        pdf = self.client.get("/api/om5/report.pdf", params={"month": "2018-06", "mode": "as_of"})
        self.assertEqual(pdf.status_code, 200); self.assertTrue(pdf.content.startswith(b"%PDF"))
        csv = self.client.get("/api/om5/kpis.csv", params={"month": "2018-06", "mode": "as_of"})
        self.assertEqual(csv.status_code, 200); self.assertIn(b"metric_id", csv.content)

