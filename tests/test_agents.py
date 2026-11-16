"""Tests des agents sur données synthétiques :  python -m unittest tests/test_agents.py -v
Nécessite le dépôt ShopInsight pour encoding_spec.json / baseline_results.json : variable d'environnement SHOPINSIGHT_REPO."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from agents.bo1_agent import PreventiveDiagnosisAgent  # noqa: E402
from agents.bo2_agent import VoiceOfCustomerAgent  # noqa: E402
from agents.core import EvidenceLog, verify_narrative  # noqa: E402


class FakeLLM:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), 0

    def chat(self, messages, tools=None, max_tokens=700):
        self.calls += 1
        return self.replies.pop(0)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo = os.environ.get("SHOPINSIGHT_REPO", str(ROOT))
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        subprocess.run([sys.executable, str(ROOT / "tests/make_synthetic_data.py"), "--out", str(cls.dir), "--repo", repo, "--n", "16000"], check=True, capture_output=True)
        subprocess.run([sys.executable, str(ROOT / "src/train_agent_models.py"), "--project-dir", str(cls.dir)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()


class TestVerify(unittest.TestCase):
    def test_numbers(self):
        log = EvidenceLog()
        log.add("mdl:x", "estimation", "t", {"rate": 0.124, "n": 949})
        self.assertTrue(verify_narrative("Taux de 12,4 % sur 949 commandes.", log)[0])
        self.assertFalse(verify_narrative("Taux de 31 % sur 949 commandes.", log)[0])
        self.assertFalse(verify_narrative("Voir mdl:inconnu.", log)[0])


class TestBO1(Base):
    def setUp(self):
        self.ag = PreventiveDiagnosisAgent(self.dir)
        t = self.ag.store.features("test").sort_values("order_purchase_timestamp")
        self.oid = t.iloc[300]["order_id"]

    def test_no_leak_and_audit(self):
        r = self.ag.diagnose(self.oid, audit=False)
        self.assertIsNone(self.ag.log.get(f"ord:{self.oid}:issue"))
        r2 = self.ag.diagnose(self.oid, audit=True)
        self.assertIsNotNone(self.ag.log.get(f"ord:{self.oid}:issue"))
        self.assertTrue(any("RÉTROSPECTIF" in l.text for l in r2.facts))

    def test_llm_narrative_verified_or_rejected(self):
        p = self.ag.diagnose(self.oid, use_llm=False).estimates[0].evidence[0]
        pc = self.ag.log.get(p).payload["percentile_points"]
        good = {"content": f"Cette commande se situe au percentile {pc} du risque de retard."}
        self.ag.llm = FakeLLM([good])
        r = self.ag.diagnose(self.oid)
        self.assertEqual(r.narrative_source, "llm_verifie")
        bad = {"content": "Il y a 87 % de chances que ce colis soit en retard."}
        self.ag.llm = FakeLLM([bad])
        r = self.ag.diagnose(self.oid)
        self.assertEqual(r.narrative_source, "deterministe")
        self.assertIn("llm_narrative_rejected", r.meta)

    def test_unknown_order(self):
        with self.assertRaises(KeyError):
            self.ag.get_order_context("0" * 32)

    def test_triage(self):
        r = self.ag.triage("2018-06")
        self.assertIn("10 %", r.facts[0].text)

    def test_ask_routing(self):
        self.assertIn("Diagnostic", self.ag.ask(f"Diagnostic de {self.oid}").title)
        self.assertIn("surveiller", self.ag.ask("quelles commandes surveiller en 2018-06 ?").title)


class TestBO2(Base):
    def setUp(self):
        self.ag = VoiceOfCustomerAgent(self.dir)

    def test_alert_and_new_term(self):
        r = self.ag.report("2018-03", use_llm=False)
        self.assertTrue(any("ALERTE" in l.text and "Livraison" in l.text for l in r.estimates))
        r = self.ag.report("2018-07", use_llm=False)
        self.assertTrue(any("golpe" in l.text for l in r.estimates))

    def test_quotes_cited_and_labelled(self):
        r = self.ag.report("2018-03", use_llm=False)
        for l in r.similar:
            self.assertTrue(l.evidence[0].startswith("rev:"))
            self.assertTrue("traduction automatique" in l.text or "portugais original" in l.text)

    def test_small_segment_refused(self):
        r = self.ag.report("2018-03", state="GO", category="telefonia", use_llm=False)
        self.assertTrue(any("aucune conclusion fiable" in l.text for l in r.facts))

    def test_llm_tool_loop(self):
        calls = [{"tool_calls": [{"id": "1", "function": {"name": "emerging_complaints", "arguments": '{"month": "2018-03"}'}}]},
                 {"content": "Une alerte de livraison existe en mars."}]
        self.ag.llm = FakeLLM(calls)
        r = self.ag.ask("Nouvelles plaintes ?")
        self.assertIn("alerte", r.narrative)
        self.assertTrue(self.ag.log.tool_calls[0]["ok"])


if __name__ == "__main__":
    unittest.main()
