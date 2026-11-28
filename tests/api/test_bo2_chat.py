"""Assistant de la page Voix du client (/api/bo2/chat) : réponses déterministes, chaque phrase avec des preuves existantes."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HAS_DATA = (ROOT / "data/silver/reviews_text.jsonl.gz").exists()


@unittest.skipUnless(HAS_DATA, "données réelles absentes")
class TestBo2Chat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.cm = TestClient(app)
        cls.c = cls.cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.cm.__exit__(None, None, None)

    def ask(self, q, month="2018-03"):
        r = self.c.post("/api/bo2/chat", json={"question": q, "month": month})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_emerging_alert_march_2018(self):
        d = self.ask("Quelles plaintes augmentent ce mois-ci ?")
        self.assertTrue(any("Livraison et délais" in it["texte"] for it in d["items"]))

    def test_every_item_cites_known_evidence(self):
        for q in ["De quoi se plaignent le plus les clients ?", "Montre-moi des avis sur la livraison", "Que faut-il faire en priorité ?"]:
            d = self.ask(q)
            ids = {e["id"] for e in d["evidence"]}
            self.assertTrue(d["items"])
            for it in d["items"]:
                self.assertTrue(it["preuves"], it)
                self.assertTrue(set(it["preuves"]) <= ids, it)

    def test_month_in_question_wins(self):
        self.assertEqual(self.ask("Quelles plaintes augmentent en mars 2018 ?", month="2018-08")["month"], "2018-03")


if __name__ == "__main__":
    unittest.main()
