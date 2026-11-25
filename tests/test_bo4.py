import subprocess, sys, tempfile, types, unittest
from pathlib import Path
from unittest import mock
import joblib
import numpy as np

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"src"))
from agents.bo4_agent import CustomerAssistantAgent
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

if __name__=="__main__":unittest.main()
