"""Evaluate BO4 on 60 real historical scenarios without external LLM calls."""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from agents.bo4_agent import CustomerAssistantAgent

QUESTIONS=["Quand arrivera ma commande ?","Où en est ma commande ?","D'autres clients ont-ils signalé un retard ?",
           "Há relatos de produto errado?","Mon article risque-t-il d'être manquant ?","Que faire si la date promise est dépassée ?",
           "Le vendeur répond-il aux clients ?"]

class HallucinatingLLM:
    def chat(self,*args,**kwargs):return {"content":"Le transporteur a perdu le colis. Remboursement garanti."}

def main():
    p=argparse.ArgumentParser();p.add_argument("--project-dir",type=Path,default=Path("."));p.add_argument("--scenarios",type=int,default=60);a=p.parse_args();root=a.project_dir.resolve()
    agent=CustomerAssistantAgent(root);orders=agent.store.orders
    eligible=orders[(orders.order_purchase_timestamp>="2018-04-01")&(orders.order_purchase_timestamp<"2018-09-01")&orders.order_approved_at.notna()].sort_values("order_purchase_timestamp")
    sample=eligible.iloc[np.linspace(0,len(eligible)-1,min(a.scenarios,len(eligible)),dtype=int)];checks=[]
    for i,(_,row) in enumerate(sample.iterrows()):
        started=time.perf_counter();report=agent.answer_customer_question(row.order_id,QUESTIONS[i%len(QUESTIONS)],row.order_approved_at);lat=(time.perf_counter()-started)*1000
        ids=agent.log.ids();all_lines=report.facts+report.estimates+report.similar+report.actions
        citations=all(ref in ids for line in all_lines for ref in line.evidence)
        temporal=True
        for ev in agent.log.with_prefix("rev:"):
            temporal &= ev.payload.get("published_at","") <= row.order_approved_at.isoformat()
        for ev in agent.log.with_prefix("ord:similar:"):
            temporal &= all(str(case.get("order_delivered_customer_date","")) <= row.order_approved_at.isoformat() for case in ev.payload.get("cases",[]))
        timeline=agent.get_order_timeline(row.order_id,row.order_approved_at)
        temporal &= all(e["at"]<=row.order_approved_at.isoformat() for e in timeline["events"])
        uncertainty=any("80 %" in line.text or "intervalle" in line.text.lower() or "estimation" in line.text.lower() for line in report.estimates+report.actions)
        factual=report.meta.get("as_of","").startswith(row.order_approved_at.date().isoformat()) and bool(report.facts)
        checks.append({"order_id":row.order_id,"as_of":row.order_approved_at.isoformat(),"factual_correctness":factual,"evidence_citation_valid":citations,
                       "temporal_integrity":bool(temporal),"uncertainty_communication":uncertainty,"latency_ms":lat})
        if (i+1)%10==0:print(f"{i+1}/{len(sample)} scénarios",flush=True)
    agent.llm=HallucinatingLLM();row=sample.iloc[0];rejected=agent.answer_customer_question(row.order_id,"Pourquoi ce retard ?",row.order_approved_at)
    hallucination_rejected=rejected.narrative_source=="deterministe" and "llm_narrative_rejected" in rejected.meta
    keys=("factual_correctness","evidence_citation_valid","temporal_integrity","uncertainty_communication")
    result={"status":"evaluated","scenarios":len(checks),"rates":{k:float(np.mean([x[k] for x in checks])) for k in keys},
            "hallucination_rejection":hallucination_rejected,"latency_ms":{"mean":float(np.mean([x["latency_ms"] for x in checks])),"p95":float(np.quantile([x["latency_ms"] for x in checks],.95))},
            "note":"Deterministic historical replay on real Olist data; no external LLM or fabricated labels."}
    (root/"quality/bo4_agent_evaluation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8");print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
