"""REHEARSE — premiers modèles de référence pour DS1.1 (retard) et DS1.2 (note 1-2).

Trois niveaux comparés sur la période TEST (avr.–août 2018), jamais vue à l'entraînement :
  0. Référence naïve : taux de retard historique de l'État du client (règle métier simple)
  1. Régression logistique (variables standardisées, classes pondérées)
  2. Gradient boosting (HistGradientBoosting de scikit-learn)
Le modèle est choisi sur VALID (janv.–mars 2018), puis ré-entraîné sur TRAIN+VALID avant l'évaluation TEST.
Métrique principale : PR-AUC (classes déséquilibrées) ; aussi ROC-AUC, Brier et précision/rappel au seuil du top 10 %.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def at_top(y, p, share=0.10):
    k = max(1, int(len(p) * share))
    idx = np.argsort(-p)[:k]
    tp = y[idx].sum()
    return float(tp / k), float(tp / max(1, y.sum()))


def evaluate(y, p):
    prec, rec = at_top(y, p)
    return {"pr_auc": round(average_precision_score(y, p), 4), "roc_auc": round(roc_auc_score(y, p), 4),
            "brier": round(brier_score_loss(y, p), 4), "precision_top10": round(prec, 4), "recall_top10": round(rec, 4),
            "prevalence": round(float(y.mean()), 4), "n": int(len(y))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    p = ap.parse_args().project_dir.resolve()
    spec = json.loads((p / "quality/encoding_spec.json").read_text())
    feats = spec["features"]
    d = {s: pd.read_csv(p / f"data/model/features_{s}.csv.gz") for s in ["train", "valid", "test"]}
    results = {}
    for target, elig, short in [("is_late", "late_label_eligible", "late"), ("is_poor_review", "poor_review_label_eligible", "poor")]:
        # les encodages par la cible propres à l'AUTRE cible ne sont pas utilisés
        X_cols = [c for c in feats if not (c.startswith("te_") and not c.endswith(f"_{short}"))]
        sets = {s: d[s][d[s][elig].astype(bool)] for s in d}
        Xtr, ytr = sets["train"][X_cols].values, sets["train"][target].astype(int).values
        Xva, yva = sets["valid"][X_cols].values, sets["valid"][target].astype(int).values
        Xte, yte = sets["test"][X_cols].values, sets["test"][target].astype(int).values
        Xtv, ytv = np.vstack([Xtr, Xva]), np.concatenate([ytr, yva])

        # 0. règle naïve : taux historique (TRAIN+VALID) de l'État du client
        state_cols = [c for c in X_cols if c.startswith("state_")]
        tv = pd.concat([sets["train"], sets["valid"]])
        st_tv = tv[state_cols].values.argmax(1)
        rate = pd.Series(ytv).groupby(st_tv).mean()
        naive = pd.Series(sets["test"][state_cols].values.argmax(1)).map(rate).fillna(ytv.mean()).values

        models = {
            "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)),
            "gradient_boosting": lambda: HistGradientBoostingClassifier(learning_rate=0.06, max_iter=400, max_leaf_nodes=31,
                                                                        l2_regularization=1.0, early_stopping=True, validation_fraction=0.15, random_state=42),
        }
        res = {"state_rate_rule": {"valid": None, "test": evaluate(yte, naive)}}
        fitted = {}
        for name, make in models.items():
            mdl = make().fit(Xtr, ytr)
            val = evaluate(yva, mdl.predict_proba(Xva)[:, 1])
            final = make().fit(Xtv, ytv)
            fitted[name] = final
            res[name] = {"valid": val, "test": evaluate(yte, final.predict_proba(Xte)[:, 1])}
        best = max(models, key=lambda n: res[n]["valid"]["pr_auc"])
        imp = permutation_importance(fitted[best], Xte, yte, scoring="average_precision", n_repeats=3, random_state=0, n_jobs=1)
        top = sorted(zip(X_cols, imp.importances_mean), key=lambda t: -t[1])[:8]
        results[target] = {"models": res, "selected_on_valid": best, "top_features_test": [[c, round(float(v), 4)] for c, v in top],
                           "n_features": len(X_cols)}
    (p / "quality/baseline_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
