"""Real-data regression for the BO4 question path that previously returned 500."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

ORDER_ID = "53cdb2fc8bc7dce0b6741e2150273451"
BEFORE = "2018-07-27T23:59:59"
AFTER = "2018-08-31T23:59:59"
QUESTIONS = [
    "Où en est ma commande ?",
    "Quand devrait-elle arriver ?",
    "D'autres clients ont-ils connu un retard similaire ?",
    "Que puis-je faire si la date promise est dépassée ?",
    "Mon colis est-il perdu ?",
    "Pouvez-vous garantir un remboursement ?",
    "Quelle est la position GPS exacte ?",
]


@unittest.skipUnless(
    (ROOT / "data/model/bo4_eta.joblib").exists()
    and (ROOT / "data/model/bo4_review_embeddings.joblib").exists()
    and (ROOT / "data/silver/orders_analysis.csv.gz").exists(),
    "artefacts BO4 réels absents",
)
class TestBO4RealRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["SHOPINSIGHT_PROJECT_DIR"] = str(ROOT)
        os.environ["SHOPINSIGHT_WARMUP"] = "0"
        # Reproduce the workstation condition: an unusable implicit HF token
        # must not affect the already-cached public BGE-M3 encoder.
        cls.old_hf_token = os.environ.get("HF_TOKEN")
        os.environ["HF_TOKEN"] = "hf_expired_or_invalid_regression_token"
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)
        if cls.old_hf_token is None:
            os.environ.pop("HF_TOKEN", None)
        else:
            os.environ["HF_TOKEN"] = cls.old_hf_token

    def test_before_and_after_delivery_are_point_in_time_safe(self):
        before = self.client.get(f"/api/bo4/orders/{ORDER_ID}/context", params={"as_of": BEFORE})
        self.assertEqual(before.status_code, 200, before.text)
        b = before.json()["result"]
        self.assertEqual(b["order"]["observable_status"], "shipped")
        self.assertNotIn("delivered", [event["event"] for event in b["timeline"]["events"]])
        self.assertTrue(b["eta"]["valid_current_estimate"])
        self.assertEqual(b["eta"]["state"], "approval_time_estimate")

        after = self.client.get(f"/api/bo4/orders/{ORDER_ID}/context", params={"as_of": AFTER})
        self.assertEqual(after.status_code, 200, after.text)
        a = after.json()["result"]
        self.assertEqual(a["order"]["observable_status"], "delivered")
        self.assertIn("delivered", [event["event"] for event in a["timeline"]["events"]])
        self.assertFalse(a["eta"]["valid_current_estimate"])
        self.assertEqual(a["eta"]["state"], "observed_delivered")

    def test_actual_ask_schema_all_questions_and_fallback(self):
        for when in (BEFORE, AFTER):
            for question in QUESTIONS:
                response = self.client.post("/api/bo4/ask", json={"order_id": ORDER_ID, "question": question, "as_of": when})
                self.assertEqual(response.status_code, 200, f"{when} / {question}: {response.text}")
                body = response.json()
                self.assertEqual(body["agent"], "bo4")
                self.assertEqual(body["report"]["narrative_source"], "deterministe")
                self.assertTrue(body["report"]["facts"])
                self.assertTrue(body["evidence"])
                ids = {item["id"] for item in body["evidence"]}
                for section in ("facts", "estimates", "similar_experiences", "actions"):
                    for line in body["report"][section]:
                        self.assertTrue(set(line["evidence"]).issubset(ids))


if __name__ == "__main__":
    unittest.main()
