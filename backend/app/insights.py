"""Données agrégées pour les graphiques des pages BO1 et BO2.

Tout est recalculé à partir des objets déjà chargés par les agents (modèles, variables, avis analysés) :
aucune nouvelle méthode de prédiction, seulement des regroupements pour l'affichage.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from agents.bo2_agent import ASPECTS
from agents.bo2_nlp import emerging_aspects
from agents.core import to_native

TARGET_COL = {"late": ("is_late", "late_label_eligible"), "poor": ("is_poor_review", "poor_review_label_eligible")}


def bo1_overview(ag, month: str, target: str = "late", top_k: int = 15) -> dict:
    """Commandes d'un mois classées par le modèle de BO1 + repères de fiabilité (déciles du test)."""
    f = ag.store.all_features
    d = f[f["order_purchase_timestamp"].dt.strftime("%Y-%m") == month]
    if d.empty:
        raise KeyError(f"Aucune commande modélisée pour {month} (mois incomplet ou hors période).")
    b = ag.bundles[target]
    sc = ag._score(target, d[b["features"]].astype(float).values)
    d = d.assign(score=sc, percentile=ag._percentile(target, sc)).sort_values("score", ascending=False)
    n_top = max(1, int(len(d) * 0.10))
    top = d.iloc[:n_top]
    orders = ag.store.orders
    ctx = orders.reindex(d.index)[["customer_state", "primary_category"]]

    # répartition des percentiles (10 tranches)
    bins = np.clip((d["percentile"].to_numpy() * 10).astype(int), 0, 9)
    hist = [{"band": f"{10 * i}–{10 * (i + 1)}", "orders": int((bins == i).sum())} for i in range(10)]

    # États les plus représentés parmi les 10 % les plus à risque, comparés à leur poids dans le mois
    st_all = ctx["customer_state"].value_counts(normalize=True)
    st_top = ctx.loc[top.index, "customer_state"].value_counts()
    states = [{"state": s, "orders": int(n), "share_top": float(n / n_top), "share_month": float(st_all.get(s, 0.0))}
              for s, n in st_top.head(8).items()]

    listing = []
    for oid in d.index[:top_k]:
        listing.append({"order_id": oid, "state": ctx.at[oid, "customer_state"], "category": ctx.at[oid, "primary_category"],
                        "promised_days": int(d.at[oid, "promised_days"]), "percentile": float(d.at[oid, "percentile"]),
                        "score": float(d.at[oid, "score"])})

    card = ag.card[target]
    deciles = [{"decile": x["decile"], "observed_rate": x["observed_rate"]} for x in card["deciles"]]

    # Vérification a posteriori sur ce mois (issues connues aujourd'hui, inconnues au moment de la décision)
    tcol, elig = TARGET_COL[target]
    lab = d[d[elig].astype(bool)]
    check = None
    if len(lab) >= 50:
        top_lab = lab.nlargest(max(1, int(len(lab) * 0.10)), "score")
        check = {"n_labelled": int(len(lab)), "base_rate": float(lab[tcol].mean()), "precision_top10pct": float(top_lab[tcol].mean()),
                 "captured": int(top_lab[tcol].sum()), "positives": int(lab[tcol].sum()), "split": str(d["split"].iloc[0])}

    # Série mensuelle : volume de commandes et taux réel, pour situer le mois
    f2 = f.assign(m=f["order_purchase_timestamp"].dt.strftime("%Y-%m"))
    g = f2[f2[elig].astype(bool)].groupby("m")[tcol].agg(["mean", "size"])
    vol = f2.groupby("m").size()
    series = [{"month": m, "orders": int(vol[m]), "rate": float(g.at[m, "mean"]) if m in g.index and g.at[m, "size"] >= 100 else None}
              for m in vol.index if vol[m] >= 100]

    return to_native({"month": month, "target": target, "n_orders": int(len(d)), "top10pct_size": n_top,
                      "top10_recall_test": card["top10_recall"], "top10_precision_test": card["top10_precision"],
                      "test_prevalence": card["test_prevalence"], "pr_auc_test": card["test_pr_auc"],
                      "histogram": hist, "deciles": deciles, "states": states, "listing": listing, "check": check, "series": series})


def _f1_summary(project_dir: Path) -> dict | None:
    p = project_dir / "quality" / "bo2_aspect_f1.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def bo2_overview(ag, month: str | None, state: str | None = None, category: str | None = None, n_months: int = 12) -> dict:
    """Profil des aspects du mois, comparaison à la référence (12 mois précédents) et évolution mensuelle."""
    month = month or ag.default_month()
    an = ag.an
    d = ag._subset(month, state, category)
    n = len(d)
    aspects = []
    for a, (label, _) in ASPECTS.items():
        col = d[f"a_{a}"]
        aspects.append({"aspect": a, "label": label, "negative": int((col == -1).sum()), "positive": int((col == 1).sum()),
                        "negative_share": float((col == -1).mean()) if n else None, "positive_share": float((col == 1).mean()) if n else None})

    emerging = emerging_aspects(an, month)
    vs_baseline = [{"aspect": r["aspect"], "label": r["label"], "rate": r["rate"], "baseline_rate": r["baseline_rate"],
                    "alert": r["alert"], "q": r["q"], "count": r["count"]} for r in emerging["aspects"]]

    # Évolution : part des avis écrits qui critiquent chaque aspect, mois par mois (périmètre filtré)
    scope = an
    if state:
        scope = scope[scope["state"] == state]
    if category:
        scope = scope[scope["category"] == category]
    months = sorted(m for m, c in scope.groupby("month").size().items() if c >= (150 if not (state or category) else 30) and m <= month)[-n_months:]
    trend = []
    for m in months:
        x = scope[scope["month"] == m]
        row = {"month": m, "n": int(len(x))}
        for a in ASPECTS:
            row[a] = float((x[f"a_{a}"] == -1).mean())
        trend.append(row)

    by_score = d.groupby("score").size().reindex(range(1, 6), fill_value=0)
    return to_native({"month": month, "state": state, "category": category, "n_reviews": int(n),
                      "share_rated_1_2": float((d["score"] <= 2).mean()) if n else None,
                      "scores": [{"score": int(s), "reviews": int(c)} for s, c in by_score.items()],
                      "aspects": aspects, "vs_baseline": vs_baseline, "baseline_months": emerging.get("baseline_months", []),
                      "alerts": [r["label"] for r in vs_baseline if r["alert"]], "trend": trend,
                      "labels": {a: v[0] for a, v in ASPECTS.items()}, "validation": _f1_summary(ag.store.dir)})
