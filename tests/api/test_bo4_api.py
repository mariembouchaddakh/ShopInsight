import os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/"src")]

class TestBO4API(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        subprocess.run([sys.executable,str(ROOT/"tests/make_synthetic_data.py"),"--out",str(cls.root),"--repo",str(ROOT),"--n","2500"],check=True,capture_output=True)
        os.environ["SHOPINSIGHT_PROJECT_DIR"]=str(cls.root);os.environ["SHOPINSIGHT_WARMUP"]="0"
        from fastapi.testclient import TestClient
        from backend.app.main import app
        cls.cm=TestClient(app);cls.client=cls.cm.__enter__()
        from agents.core import DataStore
        o=DataStore(cls.root).orders.sort_values("order_purchase_timestamp");cls.row=o[o.order_purchase_timestamp>="2018-04-01"].iloc[0]
    @classmethod
    def tearDownClass(cls): cls.cm.__exit__(None,None,None);cls.tmp.cleanup()
    def test_context_eta_similar(self):
        p={"as_of":self.row.order_approved_at.isoformat()};oid=self.row.order_id
        for suffix in ("context","eta","similar"):
            r=self.client.get(f"/api/bo4/orders/{oid}/{suffix}",params=p);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()["agent"],"bo4")
    def test_ask_and_unknown(self):
        b={"order_id":self.row.order_id,"question":"Quand arrivera ma commande ?","as_of":self.row.order_approved_at.isoformat()}
        r=self.client.post("/api/bo4/ask",json=b);self.assertEqual(r.status_code,200,r.text);self.assertTrue(r.json()["evidence"])
        self.assertEqual(self.client.get("/api/bo4/orders/"+"0"*32+"/context").status_code,404)
    def test_openapi_and_health(self):
        self.assertIn("/api/bo4/ask",self.client.get("/openapi.json").json()["paths"])
        self.assertIn("bo4",self.client.get("/api/health").json()["agents"])

if __name__=="__main__":unittest.main()
