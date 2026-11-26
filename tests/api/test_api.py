"""Tests de l'API sur les VRAIES données Olist :  python -m unittest tests/api/test_api.py -v

Prérequis : pipeline complet (prepare_data, build_model_features, train_agent_models, train_seller_models). Sinon : tests ignorés.
Vérifie notamment que les réponses BO1 / BO2 sont IDENTIQUES à un appel direct de leurs méthodes publiques (contrat inchangé).
"""
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("SHOPINSIGHT_WARMUP", "0")

FLAGGED, MONTH = "2eb70248d66e0e3ef83659f71b244378", "2018-06"
_FIX: dict = {}


def setUpModule():
    needed = ["data/silver/orders_analysis.csv.gz", "data/model/artifacts/bo3_model_card.json", "data/model/artifacts/model_late.joblib",
              "data/model/bo3_monthly_history.csv.gz"]
    missing = [p for p in needed if not (ROOT / p).exists()]
    if missing:
        raise unittest.SkipTest(f"données réelles absentes : {missing}")
    from fastapi.testclient import TestClient
    from backend.app.main import app
    _FIX["cm"] = TestClient(app)
    _FIX["client"] = _FIX["cm"].__enter__()


def tearDownModule():
    if "cm" in _FIX:
        _FIX["cm"].__exit__(None, None, None)


def roundtrip(o):
    from backend.app.serialization import jsonable
    return json.loads(json.dumps(jsonable(o)))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = _FIX["client"]


class TestPlatform(Base):
    def test_health_and_no_secret(self):
        r = self.c.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("sk-or-", r.text)
        cfg = r.json()["config"]
        self.assertIn("openrouter_key_configured", cfg)
        self.assertNotIn("openrouter_api_key", json.dumps(cfg))
        self.assertEqual(cfg["llm_budget_usd"], 0.0)

    def test_openapi(self):
        paths = self.c.get("/openapi.json").json()["paths"]
        for p in ("/api/bo1/triage", "/api/bo2/report", "/api/bo3/overview", "/api/bo3/sellers/{seller_id}/audit"):
            self.assertIn(p, paths)

    def test_log_redaction(self):
        from backend.app.logging_setup import redact
        fake = "-".join(["sk", "or", "v1", "abcdef1234567890"])  # fausse clé assemblée à l'exécution
        out = redact(f"clé {fake} et Authorization: Bearer abc.def.ghi")
        self.assertNotIn("1234567890", out)
        self.assertNotIn("abc.def.ghi", out)


class TestBO1BO2Contract(Base):
    """Les enveloppes ne changent rien : même rapport que l'appel direct de la méthode publique."""

    def test_bo1_triage_identical(self):
        from agents.bo1_agent import PreventiveDiagnosisAgent
        api = self.c.get("/api/bo1/triage", params={"month": MONTH, "target": "late", "top_k": 10}).json()["report"]
        direct = roundtrip(PreventiveDiagnosisAgent(ROOT).triage(MONTH, top_k=10, target="late").to_dict())
        self.assertEqual(api, {**direct, "section_titles": None})

    def test_bo1_diagnosis_identical_and_unknown(self):
        import pandas as pd
        from agents.bo1_agent import PreventiveDiagnosisAgent
        oid = pd.read_csv(ROOT / "data/model/features_test.csv.gz", usecols=["order_id"], nrows=50)["order_id"].iloc[10]
        api = self.c.get(f"/api/bo1/orders/{oid}/diagnosis").json()["report"]
        direct = roundtrip(PreventiveDiagnosisAgent(ROOT).diagnose(oid, use_llm=False).to_dict())
        self.assertEqual(api, {**direct, "section_titles": None})
        self.assertEqual(self.c.get("/api/bo1/orders/" + "0" * 32 + "/diagnosis").status_code, 404)
        self.assertEqual(self.c.get("/api/bo1/orders/abc/diagnosis").status_code, 422)

    def test_bo2_report_identical(self):
        from agents.bo2_agent import VoiceOfCustomerAgent
        api = self.c.get("/api/bo2/report", params={"month": "2018-03"}).json()["report"]
        direct = roundtrip(VoiceOfCustomerAgent(ROOT).report("2018-03", use_llm=False).to_dict())
        self.assertEqual(api, {**direct, "section_titles": None})


class TestBO3(Base):
    def test_audit_with_resolvable_evidence(self):
        r = self.c.get(f"/api/bo3/sellers/{FLAGGED[:8]}/audit", params={"month": MONTH})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        ids = {e["id"] for e in body["evidence"]}
        rep = body["report"]
        for block in ("facts", "estimates", "similar_experiences", "actions"):
            for line in rep[block]:
                for e in line["evidence"]:
                    self.assertIn(e, ids)
        self.assertTrue(any(l["text"].startswith("ALERTE") for l in rep["estimates"]))
        self.assertIn("# Audit vendeur", body["markdown"])

    def test_tools(self):
        cmp_ = self.c.get(f"/api/bo3/sellers/{FLAGGED}/comparison", params={"month": MONTH, "metric": "poor"}).json()
        self.assertEqual(cmp_["result"]["observed"]["recent_known_n"], 114)
        det = self.c.get(f"/api/bo3/sellers/{FLAGGED}/deterioration", params={"month": MONTH, "metric": "handover"}).json()["result"]
        self.assertTrue(det["families"]["level"]["alert"])
        hist = self.c.get(f"/api/bo3/sellers/{FLAGGED}/history", params={"month": "2018-04"}).json()["result"]
        self.assertTrue(all(x["month"] <= "2018-04" for s in hist["series"].values() for x in s))
        for path in ("profile", "peers", "strengths", "orders", "voice", "multi-seller"):
            self.assertEqual(self.c.get(f"/api/bo3/sellers/{FLAGGED}/{path}", params={"month": MONTH}).status_code, 200, path)

    def test_overview_alerts_history_meta(self):
        ov = self.c.get("/api/bo3/overview", params={"month": MONTH}).json()["result"]
        row = next(s for s in ov["sellers"] if s["seller_id"] == FLAGGED)
        self.assertTrue(row["metrics"]["poor"]["alert_level"])
        al = self.c.get("/api/bo3/alerts", params={"month": MONTH}).json()["result"]
        self.assertIn(FLAGGED, [x["seller_id"] for x in al["listing"]])
        ah = self.c.get("/api/bo3/alert-history", params={"seller_id": FLAGGED, "until": "2018-05"}).json()["result"]
        self.assertTrue(all(r["month"] <= "2018-05" for r in ah["rows"]))
        mk = self.c.get("/api/bo3/marketplace").json()["result"]
        self.assertEqual(set(mk["series"]), {"late", "poor", "handover"})
        meta = self.c.get("/api/bo3/meta").json()
        self.assertIn(MONTH, meta["decision_months"])

    def test_errors(self):
        self.assertEqual(self.c.get("/api/bo3/sellers/" + "f" * 32 + "/audit").status_code, 404)
        self.assertEqual(self.c.get(f"/api/bo3/sellers/{FLAGGED}/audit", params={"month": "06-2018"}).status_code, 422)
        self.assertEqual(self.c.get(f"/api/bo3/sellers/{FLAGGED}/comparison", params={"metric": "price"}).status_code, 422)
        self.assertEqual(self.c.post("/api/bo3/ask", json={"question": "x"}).status_code, 422)

    def test_reports_pdf_and_csv(self):
        r = self.c.get(f"/api/reports/sellers/{FLAGGED}.pdf", params={"month": MONTH})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        r = self.c.get(f"/api/reports/sellers/{FLAGGED}/evidence.csv", params={"month": MONTH})
        self.assertEqual(r.status_code, 200)
        self.assertIn("kpi:seller:2eb70248:2018-06:poor", r.content.decode("utf-8-sig"))
        self.assertEqual(self.c.get("/api/reports/sellers/" + "f" * 32 + ".pdf").status_code, 404)

    def test_llm_status_without_secret(self):
        r = self.c.get("/api/llm/status")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("sk-or-", r.text)
        self.assertEqual(r.json()["budget_usd"], 0.0)

    def test_ask(self):
        r = self.c.post("/api/bo3/ask", json={"question": "Quels vendeurs se dégradent en juin 2018 ?"}).json()
        self.assertIn("Vendeurs à investiguer", r["report"]["title"])


if __name__ == "__main__":
    unittest.main()
