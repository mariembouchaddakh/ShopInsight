import subprocess, sys, tempfile, types, unittest
from pathlib import Path
from unittest import mock
import joblib
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/"src")]
from agents.bo4_agent import CustomerAssistantAgent, detect_intent, verify_customer_narrative
from agents.bo4_eta import interval_metrics, repair_quantiles
from agents.bo4_retrieval import HistoricalReviewIndex

class TestMath(unittest.TestCase):
    def test_quantile_order_and_nonnegative(self): self.assertEqual(repair_quantiles(-2,8,4),(0.,8.,8.))
    def test_metrics(self):
        m=interval_metrics(np.array([2.,4.]),np.array([1.,3.]),np.array([2.,4.]),np.array([3.,5.]));self.assertEqual(m["picp"],1.);self.assertEqual(m["mae"],0.)

class TestBO4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        subprocess.run([sys.executable,str(ROOT/"tests/make_synthetic_data.py"),"--out",str(cls.root),"--repo",str(ROOT),"--n","3500"],check=True,capture_output=True)
        cls.ag=CustomerAssistantAgent(cls.root);o=cls.ag.store.orders.sort_values("order_purchase_timestamp");cls.oid=o[o.order_purchase_timestamp.between("2018-04-01","2018-06-01")].iloc[0].order_id
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def test_context_hides_future_delivery(self):
        r=self.ag._order(self.oid);c=self.ag.get_order_context(self.oid,r.order_approved_at);self.assertNotEqual(c["observable_status"],"delivered")
        self.assertFalse(any(x["event"]=="delivered" for x in self.ag.get_order_timeline(self.oid,r.order_approved_at)["events"]))
    def test_eta_valid_or_expired(self):
        r=self.ag._order(self.oid);e=self.ag.predict_delivery_interval(self.oid,r.order_approved_at);self.assertLessEqual(e["p10_days"],e["p50_days"]);self.assertLessEqual(e["p50_days"],e["p90_days"])
    def test_delivered_has_no_eta(self):
        r=self.ag._order(self.oid);e=self.ag.predict_delivery_interval(self.oid,r.order_delivered_customer_date+np.timedelta64(1,"D"));self.assertEqual(e["state"],"observed_delivered")
    def test_unknown_order(self):
        with self.assertRaises(KeyError): self.ag.get_order_context("0"*32,"2018-05-01")
    def test_reviews_obey_asof_and_exclude_target(self):
        r=self.ag._order(self.oid);idx=HistoricalReviewIndex(self.root,dense=False);items=idx.search("entrega atrasada",r.order_approved_at,self.oid,None,5)
        self.assertTrue(all(x["order_id"]!=self.oid and x["published_at"]<=r.order_approved_at.isoformat() for x in items))
    def test_dense_encoder_uses_cached_public_model_without_implicit_token(self):
        reviews = self.ag.store.reviews()
        joblib.dump({"model": "BAAI/bge-m3", "embeddings": np.zeros((len(reviews), 4), dtype="float32")},
                    self.root / "data/model/bo4_review_embeddings.joblib")
        seen = {}
        class FakeEncoder:
            def __init__(self, model, **kwargs): seen.update(model=model, **kwargs)
        fake_module = types.SimpleNamespace(SentenceTransformer=FakeEncoder)
        with mock.patch.dict(sys.modules, {"sentence_transformers": fake_module}):
            idx = HistoricalReviewIndex(self.root)
        self.assertIsNotNone(idx.encoder)
        self.assertEqual(seen["model"], "BAAI/bge-m3")
        self.assertTrue(seen["local_files_only"])
        self.assertIs(seen["token"], False)
    def test_future_review_does_not_change_past(self):
        r=self.ag._order(self.oid);idx=HistoricalReviewIndex(self.root,dense=False);before=idx.search("produto errado",r.order_approved_at,self.oid,None,5)
        future=idx.df.iloc[0].copy();future["review_id"]="future";future["available_at"]=r.order_approved_at+np.timedelta64(100,"D");idx.df=__import__("pandas").concat([idx.df,__import__("pandas").DataFrame([future])],ignore_index=True)
        after=idx.search("produto errado",r.order_approved_at,self.oid,None,5);self.assertEqual([x["review_id"] for x in before],[x["review_id"] for x in after])
    def test_answer_evidence_and_fallback(self):
        r=self.ag._order(self.oid);rep=self.ag.answer_customer_question(self.oid,"Quand arrivera ma commande ?",r.order_approved_at)
        ids=self.ag.log.ids();self.assertTrue(all(e in ids for block in (rep.facts,rep.estimates,rep.similar,rep.actions) for line in block for e in line.evidence))
        self.assertEqual(rep.narrative_source,"deterministe")
    def test_hallucinated_llm_claim_rejected(self):
        class Fake:
            def chat(self,*args,**kwargs): return {"content":"Le transporteur a perdu le colis, remboursement garanti."}
        r=self.ag._order(self.oid);self.ag.llm=Fake()
        rep=self.ag.answer_customer_question(self.oid,"Où est mon colis ?",r.order_approved_at);self.ag.llm=None
        self.assertEqual(rep.narrative_source,"deterministe");self.assertIn("llm_narrative_rejected",rep.meta)

    def test_intents_execute_different_minimal_tool_sets(self):
        r = self.ag._order(self.oid)
        status = self.ag.deterministic_conversation(self.oid, "Où en est ma commande ?", r.order_approved_at)
        eta = self.ag.deterministic_conversation(self.oid, "Quand arrivera-t-elle ?", r.order_approved_at)
        policy = self.ag.deterministic_conversation(self.oid, "Pouvez-vous garantir un remboursement ?", r.order_approved_at)
        self.assertEqual(status["tools"], ["get_order_context", "get_order_timeline"])
        self.assertEqual(eta["tools"], ["get_order_context", "predict_delivery_interval"])
        self.assertEqual(policy["tools"], ["get_order_context", "get_customer_options"])
        self.assertIn("No refund entitlement", " ".join(policy["results"]["get_customer_options"]["limitations"]))

    def test_short_compliment_does_not_inherit_delivery_intent(self):
        history = [{"role": "user", "content": "Quand arrivera ma commande ?"},
                   {"role": "assistant", "content": "Elle est encore en route."}]
        self.assertEqual(detect_intent("okay i love your service thanks", history), "general")

    def test_native_llm_tool_call_is_controlled_and_validated(self):
        from backend.app.llm.bo4 import converse
        from backend.app.llm.provider import LLMResult
        oid = self.oid
        class FakeProvider:
            model = "test/function-model:free"
            def __init__(self): self.calls = []
            def complete(self, messages, **kwargs):
                self.calls.append((messages, kwargs))
                if len(self.calls) == 1:
                    return LLMResult("", self.model, self.model, 0.01, tool_calls=[{"id": "call-1", "type": "function", "function": {"name": "get_order_context", "arguments": '{"order_id":"evil","as_of":"2099-01-01"}'}}])
                return LLMResult(f"Votre commande a un statut vérifié [{f'ord:{oid}'}].", self.model, self.model, 0.01)
        r = self.ag._order(oid); provider = FakeProvider()
        out = converse(self.ag, provider, oid, "Et son statut ?", r.order_approved_at.isoformat(),
                       [{"role": "user", "content": "Parlez-moi de ma commande"}])
        self.assertEqual(out["source"], "llm_verified")
        self.assertEqual(out["debug"]["selected_tools"], ["get_order_context"])
        self.assertEqual(out["debug"]["tool_calls"][0]["arguments"]["order_id"], oid)
        self.assertTrue(any(m.get("content") == "Parlez-moi de ma commande" for m in provider.calls[0][0]))
        offered = {x["function"]["name"] for x in provider.calls[0][1]["tools"]}
        self.assertEqual(offered, {"get_order_context", "get_order_timeline", "predict_delivery_interval",
                                   "find_similar_orders", "retrieve_similar_reviews"})

    def test_natural_language_dates_are_checked_against_evidence(self):
        r = self.ag._order(self.oid); self.ag.log = __import__("agents.core", fromlist=["EvidenceLog"]).EvidenceLog()
        self.ag.get_order_context(self.oid, r.order_approved_at)
        ref = f"ord:{self.oid}"
        approved = __import__("pandas").Timestamp(r.order_approved_at)
        known = f"La commande a été approuvée le {approved.day:02d}/{approved.month:02d}/{approved.year} [{ref}]."
        invented = f"La commande sera livrée le 31/12/2099 [{ref}]."
        self.assertTrue(verify_customer_narrative(known, self.ag.log)[0])
        self.assertFalse(verify_customer_narrative(invented, self.ag.log)[0])

    def test_customer_narrative_rejects_exposed_order_identifier(self):
        r = self.ag._order(self.oid); self.ag.log = __import__("agents.core", fromlist=["EvidenceLog"]).EvidenceLog()
        self.ag.get_order_context(self.oid, r.order_approved_at)
        text = f"Une autre commande comparable porte l'identifiant {self.oid} [ord:{self.oid}]."
        self.assertFalse(verify_customer_narrative(text, self.ag.log)[0])

    def test_unvalidated_llm_answer_falls_back(self):
        from backend.app.llm.bo4 import converse
        from backend.app.llm.provider import LLMResult
        class FakeProvider:
            model = "test/function-model:free"
            def complete(self, messages, **kwargs):
                return LLMResult("Le transporteur a perdu le colis et garantit un remboursement.", self.model, self.model, 0.01)
        r = self.ag._order(self.oid)
        out = converse(self.ag, FakeProvider(), self.oid, "Pourquoi ce retard ?", r.order_approved_at.isoformat())
        self.assertEqual(out["source"], "deterministic_fallback")
        self.assertEqual(out["debug"]["fallback_reason"], "validation_failed")

if __name__=="__main__":unittest.main()
