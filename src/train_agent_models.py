"""REHEARSE — modèles persistants pour l'agent BO1 (DS1.3).

Reprend exactement la logique de train_baselines.py (mêmes variables, même découpage chronologique) mais :
  - sauvegarde le modèle final (entraîné sur TRAIN+VALID) pour chaque cible ;
  - sauvegarde une ligne de référence (médiane TRAIN) pour l'explication locale ;
  - calcule la distribution des scores sur TEST (hors échantillon) et, par décile, le taux observé :
    c'est la « calibration empirique » utilisée par l'agent à la place d'une probabilité brute
    (la régression logistique à classes pondérées n'est pas calibrée ; Brier test = 0,27).

Modèle par cible : celui choisi sur VALID dans quality/baseline_results.json (règle reproductible, sans regarder TEST),
sauf si --model est donné.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

TARGETS = {"late": ("is_late", "late_label_eligible"), "poor": ("is_poor_review", "poor_review_label_eligible")}


def make_model(name: str):
    if name == "logistic":
        return make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5))
    return HistGradientBoostingClassifier(learning_rate=0.06, max_iter=400, max_leaf_nodes=31, l2_regularization=1.0,
                                          early_stopping=True, validation_fraction=0.15, random_state=42)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    ap.add_argument("--model", choices=["logistic", "gradient_boosting"], default=None, help="force le modèle pour les deux cibles")
    args = ap.parse_args()
    p = args.project_dir.resolve()
    spec = json.loads((p / "quality/encoding_spec.json").read_text())
    baseline = json.loads((p / "quality/baseline_results.json").read_text())
    d = {s: pd.read_csv(p / f"data/model/features_{s}.csv.gz") for s in ["train", "valid", "test"]}
    out = p / "data/model/artifacts"
    out.mkdir(parents=True, exist_ok=True)
    meta = {}
    for short, (target, elig) in TARGETS.items():
        cols = [c for c in spec["features"] if not (c.startswith("te_") and not c.endswith(f"_{short}"))]
        sets = {s: d[s][d[s][elig].astype(bool)] for s in d}
        name = args.model or baseline[target]["selected_on_valid"]
        tv = pd.concat([sets["train"], sets["valid"]])
        model = make_model(name).fit(tv[cols].values, tv[target].astype(int).values)
        te = sets["test"]
        score_te = model.predict_proba(te[cols].values)[:, 1]
        y = te[target].astype(int).values
        order = np.argsort(score_te)
        ref_scores = np.sort(score_te)
        # taux observé par décile de score (TEST, hors échantillon)
        edges = np.quantile(score_te, np.linspace(0, 1, 11))
        deciles = []
        for i in range(10):
            lo, hi = edges[i], edges[i + 1]
            m = (score_te >= lo) & (score_te <= hi if i == 9 else score_te < hi)
            deciles.append({"decile": i + 1, "score_min": float(lo), "score_max": float(hi), "n": int(m.sum()),
                            "observed_rate": float(y[m].mean()) if m.any() else None})
        k = max(1, int(len(y) * 0.10))
        top = np.argsort(-score_te)[:k]
        train_ref = sets["train"][cols].median()
        bundle = {"model": model, "features": cols, "reference_row": train_ref.to_dict(), "ref_scores": ref_scores,
                  "model_name": name, "target": target}
        joblib.dump(bundle, out / f"model_{short}.joblib")
        meta[short] = {"target": target, "model": name, "n_features": len(cols), "test_n": int(len(y)),
                       "test_prevalence": float(y.mean()), "test_pr_auc": float(average_precision_score(y, score_te)),
                       "top10_precision": float(y[top].mean()), "top10_recall": float(y[top].sum() / max(1, y.sum())),
                       "deciles": deciles, "trained_on": "train+valid (2016-10 → 2018-03)", "evaluated_on": "test (2018-04 → 2018-08)"}
        print(short, name, "PR-AUC test", round(meta[short]["test_pr_auc"], 4), "top10 recall", round(meta[short]["top10_recall"], 3))
    (out / "model_card.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
