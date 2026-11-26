"""Benchmark BO4 retrieval and create a pooled human-annotation dataset.

Latency and storage are measured immediately. Relevance metrics are emitted only
when an annotator has filled ``relevance_0_1_2``; blank labels are never guessed.
"""
from __future__ import annotations

import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parent))
from agents.bo4_retrieval import HistoricalReviewIndex
from agents.core import DataStore

QUERIES={"fr":["retard de livraison","article manquant","produit incorrect","emballage abîmé","mauvaise qualité","vendeur sans réponse","client satisfait"],
         "pt":["entrega atrasada","item faltando","produto errado","embalagem danificada","qualidade ruim","vendedor não respondeu","cliente satisfeito"]}
SYSTEMS=("tfidf","bm25","dense","hybrid")

def metrics(rows:pd.DataFrame)->dict:
    labelled=rows[pd.to_numeric(rows.relevance_0_1_2,errors="coerce").notna()].copy()
    if labelled.empty:return {}
    labelled["rel"]=pd.to_numeric(labelled.relevance_0_1_2);relevant={q:set(g.loc[g.rel>0,"candidate_review_id"]) for q,g in labelled.groupby("question_id")}
    out={}
    for system,g0 in labelled.groupby("system"):
        ps=[];rs=[];mrr=[];nd=[]
        for q,g in g0.sort_values("rank").groupby("question_id"):
            g=g.head(5);binary=(g.rel.to_numpy()>0).astype(int);ps.append(float(binary.mean()))
            denom=len(relevant.get(q,set()));rs.append(float(binary.sum()/denom) if denom else np.nan)
            ranks=np.flatnonzero(binary);mrr.append(float(1/(ranks[0]+1)) if len(ranks) else 0.)
            gains=(2**g.rel.to_numpy()-1)/np.log2(np.arange(2,len(g)+2));ideal=np.sort(g.rel.to_numpy())[::-1]
            ideal_score=float(np.sum((2**ideal-1)/np.log2(np.arange(2,len(ideal)+2))));nd.append(float(gains.sum()/ideal_score) if ideal_score else np.nan)
        out[system]={"precision_at_5":float(np.nanmean(ps)),"recall_at_5":float(np.nanmean(rs)),"mrr":float(np.nanmean(mrr)),"ndcg_at_5":float(np.nanmean(nd)),"questions":len(ps)}
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument("--project-dir",type=Path,default=Path("."));p.add_argument("--questions",type=int,default=100)
    p.add_argument("--annotations",type=Path,help="Previously filled pooled annotation CSV");a=p.parse_args();root=a.project_dir.resolve()
    store=DataStore(root);orders=store.orders
    eligible=orders[(orders.order_purchase_timestamp>="2018-04-01")&(orders.order_purchase_timestamp<"2018-09-01")&orders.order_approved_at.notna()].sort_values("order_purchase_timestamp")
    sample=eligible.iloc[np.linspace(0,len(eligible)-1,min(a.questions,len(eligible)),dtype=int)]
    index=HistoricalReviewIndex(root,dense=True);rows=[];lat={s:[] for s in SYSTEMS}
    for i,(_,order) in enumerate(sample.iterrows()):
        lang=("fr","pt")[i%2];query=QUERIES[lang][i%len(QUERIES[lang])];qid=f"Q{i+1:03d}"
        context={"customer_state":order.get("customer_state"),"primary_category":order.get("primary_category")}
        for system in SYSTEMS:
            started=time.perf_counter();hits=index.search(query,order.order_approved_at,order.order_id,context,5,system=system);lat[system].append((time.perf_counter()-started)*1000)
            for rank,hit in enumerate(hits,1):
                rows.append({"question_id":qid,"language":lang,"question":query,"order_id":order.order_id,"as_of":order.order_approved_at.isoformat(),
                             "system":system,"rank":rank,"candidate_review_id":hit["review_id"],"candidate_score":hit["score"],
                             "candidate_text_pt":" ".join(str(hit["text_pt"]).split()),"candidate_text_fr":" ".join(str(hit["text_fr"]).split()),"published_at":hit["published_at"],
                             "relevance_0_1_2":"","annotator":"","notes":""})
        if (i+1)%10==0:print(f"{i+1}/{len(sample)} questions",flush=True)
    frame=pd.DataFrame(rows);template=root/"quality/bo4_retrieval_annotation_template.csv";frame.to_csv(template,index=False,encoding="utf-8-sig")
    labelled=pd.read_csv(a.annotations,keep_default_na=False) if a.annotations and a.annotations.exists() else frame
    timing={s:{"mean_ms":float(np.mean(v)),"p95_ms":float(np.quantile(v,.95)),"queries":len(v)} for s,v in lat.items()}
    files={name:int((root/name).stat().st_size) for name in ("data/model/bo4_review_embeddings.joblib","data/model/bo4_reviews.faiss") if (root/name).exists()}
    scores=metrics(labelled);result={"status":"evaluated" if scores else "awaiting_human_annotations","questions":len(sample),"candidate_rows":len(frame),
      "systems":list(SYSTEMS),"latency":timing,"index_files_bytes":files,"relevance_metrics":scores,
      "note":"Precision/recall/MRR/nDCG are intentionally blank until pooled candidates receive human judgments." if not scores else "Metrics computed from supplied human judgments."}
    (root/"quality/bo4_retrieval_results.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
