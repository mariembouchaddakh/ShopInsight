"""Tests de la couche IA SANS réseau ni quota (OpenRouter simulé) :  python -m unittest tests/api/test_llm.py -v

Vérifie : refus des modèles payants ou non « :free », refus d'une substitution de modèle ou d'un coût ≠ 0, nouvelles tentatives bornées,
cache, absence de la clé dans les journaux, et validation des sorties (chiffres, preuves, causalité, marketing, hypothèses).
Le dernier test (vraies données) vérifie que sans clé l'IA répond 503 alors que l'audit déterministe reste disponible.
"""
import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from backend.app.llm import provider as prov  # noqa: E402
from backend.app.llm.analyst import validate_output, with_caveats  # noqa: E402
from backend.app.llm.provider import LLMError, OpenRouterFreeProvider  # noqa: E402
from backend.app.llm.validator import check_item, evidence_log  # noqa: E402
from backend.app.logging_setup import redact  # noqa: E402

FREE, PAID = "vendor/free-model:free", "vendor/paid-model"
FREE2 = "other/second-model:free"          # 2e modèle gratuit (autre famille) pour le repli
SNEAKY = "vendor/sneaky-model:free"        # suffixe « :free » mais prix > 0 dans le catalogue : doit être refusé
SECRET = "-".join(["sk", "or", "v1", "0123456789abcdef" * 2])  # fausse clé, assemblée à l'exécution (pas de motif de secret dans le dépôt)


def catalog(free_price="0"):
    return {"data": [{"id": FREE, "pricing": {"prompt": free_price, "completion": free_price, "request": "0"}, "context_length": 1000},
                     {"id": FREE2, "pricing": {"prompt": "0", "completion": "0", "request": "0"}, "context_length": 1000},
                     {"id": SNEAKY, "pricing": {"prompt": "0.000001", "completion": "0"}},
                     {"id": PAID, "pricing": {"prompt": "0.000001", "completion": "0.000002"}}]}


class Mock:
    def __init__(self, chat_responses, free_price="0"):
        self.chat = list(chat_responses)
        self.posts = 0
        self.models: list[str] = []  # modèles réellement appelés, dans l'ordre
        self.free_price = free_price
        self.client = httpx.Client(transport=httpx.MockTransport(self.handle))

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert SECRET not in str(request.url)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=catalog(self.free_price))
        self.posts += 1
        body = json.loads(request.content)
        assert body["provider"] == {"allow_fallbacks": False} and "models" not in body
        self.models.append(body["model"])
        status, payload = self.chat.pop(0)
        return httpx.Response(status, json=payload)


def ok(content, model=FREE, cost=0):
    return 200, {"model": model, "choices": [{"message": {"content": content}}], "usage": {"total_tokens": 10, "cost": cost}}


class TestProvider(unittest.TestCase):
    def setUp(self):
        prov._CATALOG.update({"at": 0.0, "models": {}})
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, mock, model=FREE, key=SECRET):
        return OpenRouterFreeProvider(key, model, cache_dir=Path(self.tmp.name), call_log=Path(self.tmp.name) / "calls.jsonl",
                                      client=mock.client, backoff_s=0, max_retries=2)

    def test_paid_or_non_free_models_refused_before_any_call(self):
        for model in (PAID, "vendor/free-model"):
            m = Mock([])
            with self.assertRaises(LLMError) as cm:
                self.make(m, model).complete([{"role": "user", "content": "x"}])
            self.assertEqual(cm.exception.kind, "not_free")
            self.assertEqual(m.posts, 0)

    def test_free_variant_that_became_paid_refused(self):
        m = Mock([], free_price="0.000001")
        with self.assertRaises(LLMError) as cm:
            self.make(m).complete([{"role": "user", "content": "x"}])
        self.assertEqual((cm.exception.kind, m.posts), ("not_free", 0))

    def test_substitution_and_nonzero_cost_rejected(self):
        with self.assertRaises(LLMError) as cm:
            self.make(Mock([ok("{}", model="other/model")])).complete([{"role": "user", "content": "a"}])
        self.assertEqual(cm.exception.kind, "substituted")
        with self.assertRaises(LLMError) as cm:
            self.make(Mock([ok("{}", cost=0.01)])).complete([{"role": "user", "content": "b"}])
        self.assertEqual(cm.exception.kind, "not_zero_cost")

    def test_retries_bounded_then_rate_limited(self):
        m = Mock([(429, {})] * 3)
        with self.assertRaises(LLMError) as cm:
            self.make(m).complete([{"role": "user", "content": "c"}])
        self.assertEqual((cm.exception.kind, m.posts), ("rate_limited", 3))

    def test_cache_avoids_second_call_and_no_key(self):
        m = Mock([ok('{"a": 1}')])
        p = self.make(m)
        r1 = p.complete([{"role": "user", "content": "d"}])
        r2 = p.complete([{"role": "user", "content": "d"}])
        self.assertEqual((m.posts, r1.cached, r2.cached, r2.content), (1, False, True, '{"a": 1}'))
        with self.assertRaises(LLMError) as cm:
            self.make(Mock([]), key=None).complete([{"role": "user", "content": "e"}])
        self.assertEqual(cm.exception.kind, "no_key")

    def test_mandatory_reasoning_same_model_retry(self):
        """Point d'accès qui impose le raisonnement : réessai sur le MÊME modèle (jamais un autre), avec raisonnement activé."""
        m = Mock([(400, {"error": {"message": "Reasoning is mandatory for this endpoint and cannot be disabled."}}), ok('{"x": 1}')])
        r = self.make(m).complete([{"role": "user", "content": "g"}])
        self.assertEqual((m.posts, r.model_returned, r.content), (2, FREE, '{"x": 1}'))

    def test_key_never_exposed(self):
        p = self.make(Mock([ok("{}")]))
        self.assertNotIn(SECRET, repr(p))
        p.complete([{"role": "user", "content": "f"}])
        self.assertNotIn(SECRET, (Path(self.tmp.name) / "calls.jsonl").read_text(encoding="utf-8"))
        self.assertNotIn("0123456789abcdef0123", redact(f"Authorization: Bearer {SECRET} / {SECRET}"))


class TestFailover(unittest.TestCase):
    """Repli déterministe sur une liste ordonnée de modèles gratuits (FailoverFreeProvider), sans réseau."""

    def setUp(self):
        prov._CATALOG.update({"at": 0.0, "models": {}})
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "calls.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, mock, models):
        return prov.FailoverFreeProvider(SECRET, models, cache_dir=Path(self.tmp.name), call_log=self.log, client=mock.client, backoff_s=0)

    def events(self):
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_429_on_first_model_fails_over_to_second(self):
        m = Mock([(429, {}), ok('{"a": 1}', model=FREE2)])
        p = self.make(m, [FREE, FREE2, FREE])  # doublon retiré, ordre conservé
        self.assertEqual(p.candidates, [FREE, FREE2])
        r = p.complete([{"role": "user", "content": "x"}])
        self.assertEqual((r.content, r.model_used, p.model, m.models), ('{"a": 1}', FREE2, FREE2, [FREE, FREE2]))
        self.assertEqual(r.candidates_tried, [{"model": FREE, "error": "rate_limited"}, {"model": FREE2, "status": "ok"}])
        served = [e for e in self.events() if e.get("event") == "served"]
        self.assertEqual((served[-1]["model_used"], served[-1]["fallback"]), (FREE2, True))
        self.assertNotIn(SECRET, self.log.read_text(encoding="utf-8"))

    def test_transient_and_unavailable_errors_rotate(self):
        m = Mock([(503, {}), ok('{"b": 2}', model=FREE2)])
        self.assertEqual(self.make(m, [FREE, FREE2]).complete([{"role": "user", "content": "y"}]).model_used, FREE2)
        m = Mock([(400, {"error": {"message": "No endpoints found for this model"}}), ok('{"c": 3}', model=FREE2)])
        self.assertEqual(self.make(m, [FREE, FREE2]).complete([{"role": "user", "content": "z"}]).model_used, FREE2)

    def test_non_free_candidates_rejected_by_price_guard(self):
        m = Mock([ok('{"d": 4}')])
        r = self.make(m, [PAID, SNEAKY, "vendor/free-model", FREE]).complete([{"role": "user", "content": "w"}])
        self.assertEqual(m.models, [FREE])  # aucun appel vers un modèle payant ou au prix non nul
        self.assertEqual([t.get("error") for t in r.candidates_tried], ["not_free", "not_free", "not_free", None])
        m = Mock([])
        with self.assertRaises(LLMError) as cm:
            self.make(m, [PAID, SNEAKY]).complete([{"role": "user", "content": "v"}])
        self.assertEqual((cm.exception.kind, m.posts), ("not_free", 0))

    def test_all_candidates_rate_limited_raise_429_kind(self):
        m = Mock([(429, {}), (429, {})])
        with self.assertRaises(LLMError) as cm:
            self.make(m, [FREE, FREE2]).complete([{"role": "user", "content": "u"}])
        self.assertEqual((cm.exception.kind, m.models), ("rate_limited", [FREE, FREE2]))
        self.assertEqual(self.events()[-1]["event"], "failover_exhausted")

    def test_daily_account_quota_stops_without_rotating(self):
        m = Mock([(429, {"error": {"message": "Rate limit exceeded: free-models-per-day. Add credits to unlock more requests."}})])
        with self.assertRaises(LLMError) as cm:
            self.make(m, [FREE, FREE2]).complete([{"role": "user", "content": "t"}])
        self.assertEqual((cm.exception.kind, m.models), ("quota_exhausted", [FREE]))

    def test_cached_answer_reports_model_used(self):
        m = Mock([(429, {}), ok('{"e": 5}', model=FREE2)])
        self.make(m, [FREE, FREE2]).complete([{"role": "user", "content": "s"}])
        m.chat = [(429, {})]
        r = self.make(m, [FREE, FREE2]).complete([{"role": "user", "content": "s"}])
        self.assertEqual((r.cached, r.model_used), (True, FREE2))


EVIDENCE = [{"id": "kpi:seller:2eb70248:2018-06:poor", "kind": "fait", "source": "t",
             "payload": {"recent_rate": 0.57, "recent_known_n": 114, "peer_rate": 0.1435, "label": "avis 1-2 étoiles"}}]


class TestValidator(unittest.TestCase):
    def setUp(self):
        self.log = evidence_log(EVIDENCE)
        self.kpi = EVIDENCE[0]["id"]

    def test_supported_numbers_accepted(self):
        self.assertTrue(check_item("Avis 1-2 étoiles : 57,0 % sur 90 jours (n = 114) contre 14,3 % en juin 2018.", "fait", [self.kpi], self.log).ok)

    def test_rejections(self):
        cases = [("Avis 1-2 étoiles : 61,0 % (n = 114).", "fait", [self.kpi], "chiffre non sourcé"),
                 ("Avis 1-2 étoiles élevés.", "fait", ["kpi:inconnu"], "preuve inconnue"),
                 ("Avis 1-2 étoiles élevés.", "fait", [], "fait sans preuve"),
                 ("Le stock explique les retards.", "hypothese", [self.kpi], "hypothèse non formulée"),
                 ("Les avis négatifs sont dus à cause de la qualité.", "fait", [self.kpi], "affirmation causale"),
                 ("Une campagne publicitaire améliorerait les ventes.", "action", [self.kpi], "marketing"),
                 ("Une piste serait de relire les commandes ord:… avant de généraliser.", "action", [self.kpi], "identifiant de preuve incomplet"),
                 ("Une piste serait de comparer à peer:bench:... et rev:<id>.", "action", [self.kpi], "identifiant de preuve incomplet")]
        for text, kind, cited, expected in cases:
            v = check_item(text, kind, cited, self.log)
            self.assertFalse(v.ok, text)
            self.assertTrue(any(expected in p for p in v.problems), (text, v.problems))

    def test_executive_wording_rules(self):
        """Séparateur de milliers accepté ; noms de champs, jargon statistique et identifiants recopiés refusés ; questions vérifiées."""
        log = evidence_log([{"id": "kpi:x", "kind": "fait", "source": "t", "payload": {"known_n": 17449, "recent_rate": 0.57}}])
        self.assertTrue(check_item("Sur 17 449 commandes dont l'issue est connue, 57,0 % sont concernées.", "fait", ["kpi:x"], log).ok)
        for text, expected in (("Le recent_rate atteint 57,0 %.", "nom de variable"), ("Alerte bêta-binomiale à 57,0 %.", "jargon"),
                               ("Valeur q < 0,01 pour 57,0 %.", "jargon")):
            v = check_item(text, "fait", ["kpi:x"], log)
            self.assertTrue(any(expected in p for p in v.problems), (text, v.problems))
        self.assertTrue(check_item("Les retards sont-ils dus à un changement de transporteur ?", "question", [], log).ok)
        self.assertFalse(check_item("Le vendeur a changé de transporteur.", "question", [], log).ok)
        self.assertFalse(check_item("Est-ce lié à 61,0 % des commandes ?", "question", [], log).ok)

    def test_repair_pass_merges_corrected_items(self):
        """Une passe de correction : l'élément rejeté puis corrigé est affiché, les statistiques le comptent comme réparé."""
        from backend.app.llm.analyst import analyse

        class Out:
            def __init__(self, content):
                self.content, self.model_requested, self.model_returned = content, FREE, FREE
                self.latency_s, self.usage, self.cost, self.cached, self.attempts = 0.1, {}, 0, False, 1

        class Prov:
            model = FREE

            def __init__(self, replies):
                self.replies = list(replies)

            def complete(self, messages, max_tokens=0):
                return Out(self.replies.pop(0))
        first = json.dumps({"diagnostic": [{"texte": "Avis 1-2 étoiles : 61,0 %.", "type": "fait", "preuves": [self.kpi]},
                                           {"texte": "Avis 1-2 étoiles : 57,0 % (n = 114).", "type": "fait", "preuves": [self.kpi]}]})
        fixed = json.dumps({"diagnostic": [{"texte": "Avis 1-2 étoiles à 57,0 % contre 14,3 % pour la marketplace.", "type": "fait", "preuves": [self.kpi]}]})
        res = analyse(Prov([first, fixed]), {"caveats": [], "meta": {"alerts": [{"metric": "poor"}]}}, EVIDENCE)
        self.assertEqual(len(res.sections["diagnostic"]), 2)
        self.assertEqual((res.stats["items_rejected"], res.stats["items_repaired"], res.stats["items_rejected_first_pass"]), (0, 1, 1))
        self.assertEqual(res.call["llm_calls"], 2)

    def test_answer_without_llm_is_factual_and_cited(self):
        """Réponse de secours (quota épuisé) : uniquement des faits, chacun cité et validé ; questions fréquentes couvertes."""
        from backend.app.llm.fallback import answer_without_llm
        ev = [{"id": "mdl:aspects:seller:2eb70248:2018-06", "kind": "estimation", "source": "t",
               "payload": {"available": True, "n_written_reviews": 90, "share_rated_1_2": 0.711,
                           "top_negative": [{"label": "Livraison et délais", "negative": 24}], "quotes": []}},
              {"id": "alr:list:2018-06:all", "kind": "estimation", "source": "t",
               "payload": {"n_alerted_sellers": 12, "n_alerts": 15, "listing": [{"seller_id": "2eb70248d66e0e3e", "main_category": "watches_gifts",
                           "top_severity": "élevée", "alerts": [{"metric": "poor", "recent_rate": 0.57, "baseline": 0.1435}]}]}}]
        r = answer_without_llm("Que disent les avis clients ?", ev, "seller")
        self.assertEqual(r["mode"], "sans_ia")
        self.assertTrue(r["items"] and all(i["type"] == "fait" and i["preuves"] for i in r["items"]))
        self.assertIn("71,1 %", r["items"][0]["texte"])
        m = answer_without_llm("Quels vendeurs nécessitent une action urgente ce mois-ci ?", ev, "market")
        self.assertTrue(any("2eb70248" in i["texte"] and "57,0 %" in i["texte"] for i in m["items"]))
        # question de définition : explication des indicateurs, pas la liste des alertes
        d = answer_without_llm("le n ça représente quoi ?", ev, "market")
        self.assertTrue(any("nombre de commandes" in i["texte"] for i in d["items"]))
        self.assertFalse(any("2eb70248" in i["texte"] for i in d["items"]))
        # question hors périmètre : on le dit, sans répéter une réponse sans rapport
        o = answer_without_llm("Quelle est la météo à Paris ?", ev, "market")
        self.assertEqual([i["type"] for i in o["items"]], ["inconnu"])

    def test_hedged_hypothesis_and_unknown_marketing_allowed(self):
        self.assertTrue(check_item("La qualité pourrait expliquer une partie des avis 1-2 étoiles, à vérifier.", "hypothese", [self.kpi], self.log).ok)
        self.assertTrue(check_item("Aucune donnée de campagne ou de publicité n'existe dans Olist.", "inconnu", [], self.log).ok)

    def test_validate_output_and_caveats_citable(self):
        report = {"caveats": ["Alertes confirmées dans 20,5 % des cas."]}
        ev = with_caveats(report, EVIDENCE)
        data = {"resume": "Avis 1-2 étoiles à 57,0 % (n = 114).",
                "situation": [{"texte": "Avis 1-2 étoiles à 57,0 %.", "type": "fait", "preuves": [self.kpi]},
                              {"texte": "Taux de 99,9 %.", "type": "fait", "preuves": [self.kpi]}],
                "inconnues": [{"texte": "Fiabilité : 20,5 % des alertes confirmées.", "type": "inconnu", "preuves": ["ctx:limites"]}],
                "actions": [{"faiblesse": "avis", "levier": "experience_client", "action": "Une piste serait de relire les avis récents",
                             "priorite": "haute", "preuves": [self.kpi]},
                            {"faiblesse": "avis", "action": "Il pourrait être utile de relire", "priorite": "urgente", "preuves": [self.kpi]},
                            {"faiblesse": "avis", "action": "Relire les avis récents", "priorite": "haute", "preuves": [self.kpi]}]}
        res = validate_output(data, ev, FREE)
        self.assertEqual(len(res.sections["situation"]), 1)
        self.assertEqual(len(res.sections["inconnues"]), 1)
        self.assertEqual(len(res.actions), 1)
        self.assertEqual(res.actions[0]["levier"], "experience_client")
        self.assertEqual(res.stats["items_rejected"], 3)
        self.assertTrue(any("conditionnel" in p for r in res.rejected for p in r["problems"]))
        self.assertFalse(res.schema_ok)
        self.assertFalse(validate_output(None, ev, FREE).schema_ok)


    def test_bilan_sections_and_chat_pistes(self):
        """Bilan & Plan de Remontée : sections diagnostic / positionnement validées ; une « piste » du chat doit être conditionnelle et citée."""
        from backend.app.llm.analyst import analysis_mode, check_chat_item
        data = {"diagnostic": [{"texte": "Avis 1-2 étoiles à 57,0 % sur 90 jours (n = 114).", "type": "fait", "preuves": [self.kpi]}],
                "positionnement": [{"texte": "Taux de 14,3 % pour la référence.", "type": "fait", "preuves": [self.kpi]}]}
        res = validate_output(data, EVIDENCE, FREE)
        self.assertEqual((len(res.sections["diagnostic"]), len(res.sections["positionnement"])), (1, 1))
        self.assertEqual((analysis_mode({"meta": {"alerts": [{"metric": "poor"}]}}), analysis_mode({"meta": {"alerts": []}})), ("remontee", "suivi"))
        self.assertTrue(check_chat_item("Une piste serait de relire les avis 1-2 étoiles récents.", "piste", [self.kpi], self.log).ok)
        self.assertFalse(check_chat_item("Relire les avis 1-2 étoiles récents.", "piste", [self.kpi], self.log).ok)
        self.assertFalse(check_chat_item("Une piste serait de relire les avis.", "piste", [], self.log).ok)


@unittest.skipUnless((ROOT / "data/model/artifacts/bo3_model_card.json").exists(), "données réelles absentes")
class TestDeterministicFallback(unittest.TestCase):
    def test_no_key_means_503_but_audit_available(self):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        old = {k: os.environ.get(k) for k in ("OPENROUTER_API_KEY", "SHOPINSIGHT_WARMUP")}
        os.environ.update({"OPENROUTER_API_KEY": "", "SHOPINSIGHT_WARMUP": "0"})
        logging.getLogger("shopinsight").setLevel(logging.WARNING)
        try:
            with TestClient(app) as c:
                r = c.post("/api/llm/sellers/2eb70248/analysis", json={"month": "2018-06", "model": "a"})
                self.assertEqual(r.status_code, 503)
                self.assertIn("audit déterministe reste disponible", r.json()["detail"])
                self.assertEqual(c.get("/api/bo3/sellers/2eb70248/audit", params={"month": "2018-06"}).status_code, 200)
                self.assertFalse(c.get("/api/llm/status").json()["key_configured"])
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


    def test_http_failover_200_then_clean_429_when_exhausted(self):
        """Bout en bout (API) : 429 sur le modèle principal → 200 servi par le 2e modèle gratuit ; tous à 429 → réponse factuelle sans IA."""
        from unittest import mock
        from fastapi.testclient import TestClient
        from backend.app.main import app
        from backend.app.routers import llm as llm_router
        old = os.environ.get("SHOPINSIGHT_WARMUP")
        os.environ["SHOPINSIGHT_WARMUP"] = "0"
        logging.getLogger("shopinsight").setLevel(logging.WARNING)
        answer = json.dumps({"reponse": [{"texte": "Réponse de test.", "type": "inconnu", "preuves": []}], "questions_suivantes": []})
        try:
            with tempfile.TemporaryDirectory() as tmp, TestClient(app) as c:
                for i, (responses, expected) in enumerate((([(429, {}), ok(answer, model=FREE2)], 200), ([(429, {}), (429, {})], 429))):
                    prov._CATALOG.update({"at": 0.0, "models": {}})
                    mk = Mock(responses)

                    def fake(request, slot, mk=mk, i=i):
                        return prov.FailoverFreeProvider(SECRET, [FREE, FREE2], cache_dir=Path(tmp) / str(i), call_log=Path(tmp) / "calls.jsonl",
                                                         client=mk.client, backoff_s=0)
                    with mock.patch.object(llm_router, "provider_for", fake):
                        r = c.post("/api/llm/chat", json={"month": "2018-06", "model": "a", "question": "Quels vendeurs nécessitent une action urgente ce mois-ci ?", "history": []})
                    # le chat ne renvoie plus d'erreur : tous les modèles limités → réponse factuelle tirée des preuves (mode « sans_ia »)
                    self.assertEqual(r.status_code, 200, r.text)
                    if expected == 200:
                        self.assertEqual((r.json()["model"], r.json()["call"]["model_used"]), (FREE2, FREE2))
                    else:
                        body = r.json()
                        self.assertEqual((body["mode"], body["fallback_reason"]), ("sans_ia", "rate_limited"))
                        self.assertTrue(body["items"] and all(i["type"] == "fait" and i["preuves"] for i in body["items"]))
                    self.assertEqual(mk.models, [FREE, FREE2])
        finally:
            if old is None:
                os.environ.pop("SHOPINSIGHT_WARMUP", None)
            else:
                os.environ["SHOPINSIGHT_WARMUP"] = old


if __name__ == "__main__":
    unittest.main()
