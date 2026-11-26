"""Build resumable BGE-M3 embeddings and a local FAISS index for BO4."""
from __future__ import annotations
import argparse, hashlib, json, sys, time
from pathlib import Path
import joblib
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents.core import DataStore

def main():
    p=argparse.ArgumentParser(); p.add_argument("--project-dir",type=Path,default=Path(".")); p.add_argument("--model",default="BAAI/bge-m3")
    p.add_argument("--batch-size",type=int,default=8);p.add_argument("--checkpoint-rows",type=int,default=256);p.add_argument("--refresh",action="store_true")
    a=p.parse_args(); root=a.project_dir.resolve()
    from sentence_transformers import SentenceTransformer
    import faiss
    d=DataStore(root).reviews(); text=np.where(d.full_fr.str.len()>0,d.full_fr+" "+d.full_pt,d.full_pt).tolist()
    out=root/"data/model"; out.mkdir(parents=True,exist_ok=True)
    mmap_path, state_path = out/"bo4_review_embeddings.npy", out/"bo4_review_embeddings_state.json"
    corpus_hash=hashlib.sha256("\n".join(text).encode("utf-8")).hexdigest();started=time.time()
    state={}
    if state_path.exists() and not a.refresh: state=json.loads(state_path.read_text(encoding="utf-8"))
    valid=state.get("model")==a.model and state.get("documents")==len(text) and state.get("corpus_sha256")==corpus_hash and mmap_path.exists()
    enc=SentenceTransformer(a.model)
    if valid:
        x=np.load(mmap_path,mmap_mode="r+");done=int(state.get("completed",0));print(f"Reprise à {done}/{len(text)}",flush=True)
    else:
        probe=np.asarray(enc.encode(text[:1],batch_size=1,normalize_embeddings=True),dtype="float32")
        x=np.lib.format.open_memmap(mmap_path,mode="w+",dtype="float32",shape=(len(text),probe.shape[1]));done=0
        state={"model":a.model,"documents":len(text),"dimensions":probe.shape[1],"corpus_sha256":corpus_hash,"completed":0}
    for start in range(done,len(text),a.checkpoint_rows):
        stop=min(start+a.checkpoint_rows,len(text));x[start:stop]=np.asarray(enc.encode(text[start:stop],batch_size=a.batch_size,normalize_embeddings=True,show_progress_bar=False),dtype="float32")
        x.flush();state["completed"]=stop;state_path.write_text(json.dumps(state,indent=2),encoding="utf-8")
        elapsed=time.time()-started;rate=(stop-done)/max(elapsed,1);eta=(len(text)-stop)/max(rate,1e-9)
        print(f"{stop}/{len(text)} embeddings — {elapsed/60:.1f} min, ETA {eta/60:.1f} min",flush=True)
    x=np.asarray(np.load(mmap_path,mmap_mode="r"),dtype="float32")
    joblib.dump({"model":a.model,"embeddings":x},out/"bo4_review_embeddings.joblib",compress=0)
    idx=faiss.IndexFlatIP(x.shape[1]); idx.add(x); faiss.write_index(idx,str(out/"bo4_reviews.faiss"))
    meta={"model":a.model,"documents":len(d),"dimensions":x.shape[1],"corpus_sha256":corpus_hash,"elapsed_seconds":round(time.time()-started,1),
          "embedding_bytes":int(x.nbytes),"faiss_bytes":int((out/"bo4_reviews.faiss").stat().st_size)}
    (out/"bo4_review_index_meta.json").write_text(json.dumps(meta,indent=2),encoding="utf-8");print(json.dumps(meta,indent=2),flush=True)
if __name__=="__main__": main()
