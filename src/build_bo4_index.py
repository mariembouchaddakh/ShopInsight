"""Build optional BGE-M3 embeddings and FAISS index for BO4."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import joblib
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents.core import DataStore

def main():
    p=argparse.ArgumentParser(); p.add_argument("--project-dir",type=Path,default=Path(".")); p.add_argument("--model",default="BAAI/bge-m3"); a=p.parse_args(); root=a.project_dir.resolve()
    from sentence_transformers import SentenceTransformer
    import faiss
    d=DataStore(root).reviews(); text=np.where(d.full_fr.str.len()>0,d.full_fr+" "+d.full_pt,d.full_pt).tolist()
    enc=SentenceTransformer(a.model); x=np.asarray(enc.encode(text,batch_size=32,normalize_embeddings=True,show_progress_bar=True),dtype="float32")
    out=root/"data/model"; out.mkdir(parents=True,exist_ok=True); joblib.dump({"model":a.model,"embeddings":x},out/"bo4_review_embeddings.joblib")
    idx=faiss.IndexFlatIP(x.shape[1]); idx.add(x); faiss.write_index(idx,str(out/"bo4_reviews.faiss"))
    (out/"bo4_review_index_meta.json").write_text(json.dumps({"model":a.model,"documents":len(d),"dimensions":x.shape[1]},indent=2),encoding="utf-8")
if __name__=="__main__": main()
