"""Create BO4 annotation material; score only genuinely annotated judgments."""
from __future__ import annotations
import argparse, csv, json
from pathlib import Path

THEMES=["retard de livraison","article manquant","produit incorrect","emballage endommagé","qualité du produit","communication vendeur","satisfaction client"]
def main():
    p=argparse.ArgumentParser();p.add_argument("--project-dir",type=Path,default=Path("."));a=p.parse_args();root=a.project_dir
    q=root/"quality/bo4_retrieval_annotation_template.csv";q.parent.mkdir(exist_ok=True)
    with q.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f);w.writerow(["question_id","language","question","candidate_review_id","system","relevance_0_1_2","annotator","notes"])
        for i in range(100):
            theme=THEMES[i%len(THEMES)]; lang=("fr","pt")[i%2]; text=(f"Quels clients ont parlé de {theme} ?" if lang=="fr" else f"Quais clientes falaram de {theme}?")
            w.writerow([f"Q{i+1:03d}",lang,text,"","","","",""])
    (root/"quality/bo4_retrieval_results.json").write_text(json.dumps({"status":"awaiting_human_annotations","questions":100,
      "metrics":{},"note":"No relevance scores are reported until candidate reviews receive human judgments."},indent=2),encoding="utf-8")
if __name__=="__main__":main()
