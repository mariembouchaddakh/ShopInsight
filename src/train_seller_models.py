"""REHEARSE — BO3 : choix de la référence (DS3.1) et des détecteurs de dégradation (DS3.2), sur données « à date ». Phase 1.

Protocole fixé AVANT la lecture de TEST : docs/ShopInsight_Dossier_Technique.pdf, annexe A. Règles communes au projet :
  1. comparer à une règle simple (référence : marketplace / même catégorie ; détecteurs : « taux > facteur × référence ») ;
  2. période postérieure : réglage sur 3 plis VALID glissants (décisions 2017-Q3, 2017-Q4, 2018-Q1), TEST = 2018-04..06 lu une fois ;
  3. n'utiliser que ce qui est connu à la date de décision (agents/bo3_sellers.py).

Étapes :
  a. modèle « attendu » entraîné sur TRAIN seulement → data/model/bo3_expected.csv.gz (information observé / attendu) ;
  b. DS3.1 : la référence prédit-elle le taux futur du vendeur ? (perte log par pli ; stabilité) ;
  c. DS3.2 : détecteurs × grilles × seuil de volume, choisis sur la moyenne des plis sous plafond d'alertes ; puis règle de persistance ;
  d. sévérité (règle fixe), points forts, valeur prédictive des segments descriptifs ;
  e. dégradations injectées (+5 / +10 / +20 points) sur TEST ;
  f. historique mensuel par vendeur (data/model/bo3_monthly_history.csv.gz) et historique des alertes (data/gold/seller_alert_history.csv).
Sorties : data/model/artifacts/bo3_model_card.json, quality/bo3_model_results.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import adjusted_rand_score, brier_score_loss

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents.bo3_sellers import (ALL_DECISION_MONTHS, DETECTORS, METRICS, SEVERITY_RULE, SPLIT_MONTHS, VALID_FOLDS,  # noqa: E402
                                DetectionParams, PeerConfig, SellerData, alerts, apply_gate, decision_date, evaluate, gate_of, inject,
                                month_frame, peer_prediction_loss, previous_alerts, severity, strengths)
from agents.core import DataStore  # noqa: E402
from train_agent_models import make_model  # noqa: E402

MAX_ALERT_SHARE = 0.10  # charge d'investigation : au plus 10 % des cas éligibles (vendeur × indicateur) alertés, dans chaque pli VALID
LEVEL_ALL_METRICS = [d for d, v in DETECTORS.items() if v[0] == "level" and d != "observe_attendu"]
TREND = [d for d, v in DETECTORS.items() if v[0] == "trend"]


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def git_commit(p: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=p, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return None


def fit_expected(p: Path, store: DataStore) -> tuple[pd.DataFrame, dict]:
    """Probabilités attendues par commande, modèle entraîné sur TRAIN SEULEMENT (les modèles BO1 persistés ont vu VALID)."""
    spec_path = p / "quality/encoding_spec.json"
    if not spec_path.exists():
        return pd.DataFrame(), {"available": False, "reason": "quality/encoding_spec.json absent"}
    spec = json.loads(spec_path.read_text())
    try:
        feats = {s: store.features(s) for s in ("train", "valid", "test")}
    except FileNotFoundError as e:
        return pd.DataFrame(), {"available": False, "reason": str(e)}
    out = pd.concat([feats[s][["order_id"]].assign(split=s) for s in feats], ignore_index=True)
    meta = {"available": True, "model": "HistGradientBoosting (sans pondération de classes, donc proche d'une probabilité)",
            "trained_on": "TRAIN (achats < 2018-01-01)", "in_sample_note": "probabilités dans l'échantillon pour les commandes TRAIN"}
    for short, target, elig in (("late", "is_late", "late_label_eligible"), ("poor", "is_poor_review", "poor_review_label_eligible")):
        cols = [c for c in spec["features"] if not (c.startswith("te_") and not c.endswith(f"_{short}"))]
        tr = feats["train"][feats["train"][elig].astype(bool)]
        model = make_model("gradient_boosting").fit(tr[cols].astype(float).values, tr[target].astype(int).values)
        out[f"e_{short}"] = np.concatenate([model.predict_proba(feats[s][cols].astype(float).values)[:, 1] for s in ("train", "valid", "test")])
        va = feats["valid"][feats["valid"][elig].astype(bool)]
        meta[short] = {"n_train": int(len(tr)), "features": len(cols),
                       "valid_brier": round(float(brier_score_loss(va[target].astype(int), model.predict_proba(va[cols].astype(float).values)[:, 1])), 4),
                       "valid_mean_pred": round(float(model.predict_proba(va[cols].astype(float).values)[:, 1].mean()), 4),
                       "valid_rate": round(float(va[target].astype(float).mean()), 4)}
    return out, meta


def stability(sd: SellerData, cfg: PeerConfig, months: list[str], cache: dict) -> float | None:
    """knn : recouvrement de Jaccard des pairs d'un mois à l'autre ; groupes : indice de Rand ajusté sur les vendeurs communs."""
    vals = []
    prev = None
    for m in months:
        _, pm = month_frame(sd, m, "late", cfg, DetectionParams(), cache, with_cusum=False)
        cur = pm.group_sets() if pm else {}
        if prev:
            common = sorted(set(prev) & set(cur))
            if len(common) >= 5:
                if cfg.method == "knn":
                    vals.append(np.mean([len(prev[s] & cur[s]) / len(prev[s] | cur[s]) for s in common if prev[s] | cur[s]]))
                elif cfg.method != "global":
                    vals.append(adjusted_rand_score([prev[s] for s in common], [cur[s] for s in common]))
        prev = cur
    return round(float(np.mean(vals)), 3) if vals else None


def fold_months() -> dict[str, list[str]]:
    return {**{f"valid_{k}": v for k, v in VALID_FOLDS.items()}, "test": SPLIT_MONTHS["test"]}


def ds31(sd: SellerData, configs: list[PeerConfig], cache: dict) -> tuple[PeerConfig, dict]:
    """DS3.1 : le taux de référence prédit-il le taux futur du vendeur ? Choix : perte log moyenne sur les 3 plis VALID."""
    res: dict = {}
    for cfg in configs:
        r = {"label": cfg.label}
        for split, months in fold_months().items():
            r[split] = {}
            for metric in METRICS:
                if not sd.available[metric]:
                    continue
                f = pd.concat([month_frame(sd, m, metric, cfg, DetectionParams(), cache, with_cusum=False)[0] for m in months])
                r[split][metric] = {"peer_rate": peer_prediction_loss(f, "p_peer"), "seller_shrunk_to_peers": peer_prediction_loss(f, "p_shrunk")}
        r["stability"] = stability(sd, cfg, SPLIT_MONTHS["valid"] + SPLIT_MONTHS["test"], cache)
        res[cfg.key] = r
    glob = res["global"]

    def rel(key: str, split: str) -> float | None:
        v = [res[key][split][m]["peer_rate"]["logloss"] / glob[split][m]["peer_rate"]["logloss"]
             for m in res[key][split] if res[key][split][m]["peer_rate"]["logloss"] and glob[split][m]["peer_rate"]["logloss"]]
        return round(float(np.mean(v)), 4) if v else None

    for key in res:
        res[key]["relative_logloss_vs_global"] = {s: rel(key, s) for s in fold_months()}
        folds = [res[key]["relative_logloss_vs_global"][f"valid_{k}"] for k in VALID_FOLDS]
        res[key]["relative_logloss_vs_global"]["valid_mean"] = round(float(np.mean([x for x in folds if x is not None])), 4)
    ranked = sorted(configs, key=lambda c: (res[c.key]["relative_logloss_vs_global"]["valid_mean"], c.method != "global"))
    best = ranked[0]
    return best, {"configs": res, "selected": best.key,
                  "selection_rule": "perte log moyenne sur les 3 plis VALID (2017-Q3, 2017-Q4, 2018-Q1) du taux de référence → taux futur, relative à la marketplace"}


def folds_eval(G: pd.DataFrame, alert: pd.Series, fam: str, gate_col: str | None = None) -> tuple[dict, float, float]:
    per = {}
    for fold, months in VALID_FOLDS.items():
        m = G["month"].isin(months)
        per[fold] = evaluate(G[m], alert[m], fam, gate_col)
    mean_f1 = round(float(np.mean([v["f1"] for v in per.values()])), 4)
    max_share = max(v["alert_share_of_eligible"] for v in per.values())
    return per, mean_f1, max_share


def rule_key(mean_f1: float, max_share: float, n_alerts: int) -> tuple:
    within = max_share <= MAX_ALERT_SHARE
    return (within, mean_f1 if within else -max_share, -n_alerts)


def tune_detectors(F: pd.DataFrame, mh_grid: list[int], min_recent: int) -> tuple[dict, dict, dict]:
    gated = {mh: apply_gate(F, mh, min_recent) for mh in mh_grid}
    out: dict = {}
    for det, (fam, desc, _, grid) in DETECTORS.items():
        best = None
        for mh in mh_grid:
            G = gated[mh]
            if det == "observe_attendu":
                G = G[G["metric"].isin(["late", "poor"])]
            gc = gate_of(det, G)
            for prm in grid:
                a = alerts(G, det, prm)
                per, mf1, mshare = folds_eval(G, a, fam, gc)
                key = rule_key(mf1, mshare, int(a[G["month"].isin(sum(VALID_FOLDS.values(), []))].sum()))
                if best is None or key > best[0]:
                    best = (key, mh, prm, per, mf1, mshare)
        _, mh, prm, per, mf1, mshare = best
        G = gated[mh] if det != "observe_attendu" else gated[mh][gated[mh]["metric"].isin(["late", "poor"])]
        gc = gate_of(det, G)
        a = alerts(G, det, prm)
        T = G["month"].isin(SPLIT_MONTHS["test"])
        res = {"family": fam, "description": desc, "min_history": mh, "params": prm, "gate": gc,
               "valid_folds": per, "valid_mean_f1": mf1, "valid_max_alert_share": mshare, "valid": per["2018Q1"],
               "test": evaluate(G[T], a[T], fam, gc),
               "test_by_metric": {m: evaluate(G[T & (G["metric"] == m)], a[T & (G["metric"] == m)], fam, gc) for m in G.loc[T, "metric"].unique()}}
        out[det] = res
    chosen = {}
    for fam, pool in (("level", LEVEL_ALL_METRICS), ("trend", TREND)):
        d = max(pool, key=lambda k: rule_key(out[k]["valid_mean_f1"], out[k]["valid_max_alert_share"], out[k]["valid_folds"]["2018Q1"]["alerts"]))
        chosen[fam] = {"detector": d, "params": out[d]["params"], "min_history": out[d]["min_history"], "description": out[d]["description"],
                       "persistence": False}
    return out, chosen, gated


def family_alerts(G: pd.DataFrame, c: dict) -> tuple[pd.Series, pd.Series]:
    """Alertes de base et alertes persistantes (aussi en alerte au mois précédent) d'une famille, sur un cadre multi-mois."""
    a = alerts(G, c["detector"], c["params"])
    return a, a & previous_alerts(G, a)


def persistence_eval(gated: dict, chosen: dict) -> dict:
    out = {}
    for fam, c in chosen.items():
        G = gated[c["min_history"]]
        gc = gate_of(c["detector"], G)
        a, ap_ = family_alerts(G, c)
        T = G["month"].isin(SPLIT_MONTHS["test"])
        base = folds_eval(G, a, fam, gc)
        pers = folds_eval(G, ap_, fam, gc)
        adopt = rule_key(pers[1], pers[2], 0)[:2] > rule_key(base[1], base[2], 0)[:2]
        out[fam] = {"base": {"valid_mean_f1": base[1], "valid_max_alert_share": base[2], "valid_folds": base[0], "test": evaluate(G[T], a[T], fam, gc)},
                    "persistent": {"valid_mean_f1": pers[1], "valid_max_alert_share": pers[2], "valid_folds": pers[0], "test": evaluate(G[T], ap_[T], fam, gc)},
                    "adopted": bool(adopt)}
        chosen[fam]["persistence"] = bool(adopt)
    return out


def severity_eval(gated: dict, chosen: dict) -> dict:
    """Précision par niveau de sévérité (règle fixe) des alertes de niveau retenues."""
    c = chosen["level"]
    G = gated[c["min_history"]]
    a, ap_ = family_alerts(G, c)
    final = ap_ if c["persistence"] else a
    prev = previous_alerts(G, a)
    sev = pd.Series([severity(q, p_) for q, p_ in zip(G["level_q"], prev)], index=G.index)
    out = {"rule": SEVERITY_RULE}
    for split, months in {"valid_all_folds": sum(VALID_FOLDS.values(), []), "test": SPLIT_MONTHS["test"]}.items():
        m = G["month"].isin(months) & final & G["eval_evaluable"].astype(bool)
        out[split] = {}
        for tier in ("élevée", "moyenne", "faible"):
            mm = m & (sev == tier)
            out[split][tier] = {"alerts_evaluable": int(mm.sum()),
                                "precision": round(float(G.loc[mm, "eval_truth_level"].mean()), 4) if mm.any() else None}
    return out


def strengths_eval(gated: dict, chosen: dict, alpha: float = 0.05) -> dict:
    G = gated[chosen["level"]["min_history"]]
    s = strengths(G, alpha)
    out = {"definition": f"12 mois d'issues connues sous la référence, binomial unilatéral inférieur, BH q < {alpha} ; "
                         "vérité : taux des 60 jours suivants ≤ référence (≥ 10 commandes)", "alpha": alpha}
    for split, months in {**{f"valid_{k}": v for k, v in VALID_FOLDS.items()}, "test": SPLIT_MONTHS["test"]}.items():
        m = G["month"].isin(months)
        ev = m & G["eligible_strength"] & G["eval_evaluable_strength"].astype(bool)
        flagged = ev & s
        base = float(G.loc[ev, "eval_truth_strength"].mean()) if ev.any() else None
        prec = float(G.loc[flagged, "eval_truth_strength"].mean()) if flagged.any() else None
        out[split] = {"flagged": int((m & s).sum()), "flagged_per_month": round(float((m & s).sum()) / len(months), 1),
                      "evaluable_flagged": int(flagged.sum()), "precision": None if prec is None else round(prec, 4),
                      "base_rate": None if base is None else round(base, 4), "lift": None if not (prec and base) else round(prec / base, 2)}
    return out


def segmentation_eval(F: pd.DataFrame, prior_strength: float) -> dict:
    """Valeur PRÉDICTIVE des segments descriptifs : rétrécir l'historique du vendeur vers la référence de son segment
    (volume × région) plutôt que vers la marketplace améliore-t-il la prédiction du taux des 60 jours suivants ?"""
    f = F.copy()
    f["segment"] = f["segment_volume"].astype(str) + " | " + f["segment_region"].astype(str)
    g = f.groupby(["month", "metric", "segment"])[["year_x", "year_n"]].transform("sum")
    n_other, x_other = g["year_n"] - f["year_n"], g["year_x"] - f["year_x"]
    with np.errstate(invalid="ignore", divide="ignore"):
        p_seg = np.where(n_other >= 30, x_other / n_other.clip(lower=1), f["p_peer"])
    f["p_seg"] = np.clip(p_seg, 1e-3, 0.999)
    s = prior_strength
    f["p_shrunk_seg"] = (f["year_x"] + s * f["p_seg"]) / (f["year_n"] + s)
    out = {"segments": "volume sur 12 mois (terciles) × région du vendeur (Sudeste, Sul, autres)"}
    for split, months in fold_months().items():
        out[split] = {}
        for metric in f["metric"].unique():
            sub = f[f["month"].isin(months) & (f["metric"] == metric)]
            a, b = peer_prediction_loss(sub, "p_shrunk"), peer_prediction_loss(sub, "p_shrunk_seg")
            out[split][metric] = {"shrunk_to_reference_logloss": a["logloss"], "shrunk_to_segment_logloss": b["logloss"],
                                  "relative": round(b["logloss"] / a["logloss"], 4) if a["logloss"] else None}
    rel = [out[k][m]["relative"] for k in out if k.startswith("valid_") for m in out[k] if out[k][m]["relative"]]
    out["valid_mean_relative"] = round(float(np.mean(rel)), 4) if rel else None
    out["conclusion"] = ("le segment améliore la prédiction sur VALID" if out["valid_mean_relative"] and out["valid_mean_relative"] < 0.995
                         else "aucun gain prédictif sur VALID : segments présentés comme descriptifs uniquement")
    return out


def injection_benchmark(sd: SellerData, cfg: PeerConfig, chosen: dict, base: DetectionParams, seed: int, n_sellers: int) -> dict:
    rng = np.random.default_rng(seed)
    start_month, months = "2018-03", ["2018-04", "2018-05", "2018-06"]
    start = decision_date(start_month)
    mh_min = min(c["min_history"] for c in chosen.values())
    out: dict = {"start": str(start.date()), "months": months, "note": "issues 0 → 1 tirées au hasard pour les vendeurs choisis, achats ≥ début ; "
                 "règle de persistance appliquée si retenue", "by_metric": {}}
    for metric in METRICS:
        if not sd.available[metric]:
            continue
        f0, _ = month_frame(sd, start_month, metric, cfg, base, {})
        f0 = f0.reset_index()
        g0 = {fam: apply_gate(f0, c["min_history"], base.min_recent) for fam, c in chosen.items()}
        prev_hits = {fam: set(g0[fam].loc[alerts(g0[fam], c["detector"], c["params"]), "seller_id"]) for fam, c in chosen.items()}
        quiet = set(f0.loc[(f0["year_n"] >= mh_min) & (f0["rec_n"] >= base.min_recent), "seller_id"]) - set().union(*prev_hits.values())
        pool = sorted(quiet)
        if not pool:
            continue
        chosen_sellers = list(rng.choice(pool, size=min(n_sellers, len(pool)), replace=False))
        res_m = {"n_injected_sellers": len(chosen_sellers)}
        for delta in (0.05, 0.10, 0.20):
            sdi = inject(sd, chosen_sellers, metric, start, delta, seed)
            cache: dict = {}
            first: dict = {}
            fa, el = [], []
            prev = {fam: set(v) for fam, v in prev_hits.items()}
            for i, m in enumerate(months, 1):
                f, _ = month_frame(sdi, m, metric, cfg, base, cache)
                f = f.reset_index()
                hit = pd.Series(False, index=f.index)
                for fam, c in chosen.items():
                    raw = alerts(apply_gate(f, c["min_history"], base.min_recent), c["detector"], c["params"])
                    now = set(f.loc[raw, "seller_id"])
                    final = raw & f["seller_id"].isin(prev[fam]) if c.get("persistence") else raw
                    prev[fam] = now
                    hit |= final
                for s_ in f.loc[hit & f["seller_id"].isin(chosen_sellers), "seller_id"]:
                    first.setdefault(s_, i)
                others = ~f["seller_id"].isin(chosen_sellers) & (f["year_n"] >= mh_min) & (f["rec_n"] >= base.min_recent)
                fa.append(int((hit & others).sum()))
                el.append(int(others.sum()))
            n = len(chosen_sellers)
            res_m[f"+{int(delta * 100)}_points"] = {
                "detected_by_month": {m: round(sum(1 for v in first.values() if v <= i) / n, 3) for i, m in enumerate(months, 1)},
                "median_delay_months": float(np.median(list(first.values()))) if first else None,
                "false_alarm_rate_untouched": round(sum(fa) / max(1, sum(el)), 4)}
        out["by_metric"][metric] = res_m
    return out


HISTORY_COLUMNS = ["month", "metric", "seller_id", "rec_n", "rec_x", "rec_rate", "year_n", "year_rate", "p_peer", "p_hist", "level_q",
                   "eligible", "eligible_trend", "alert_level", "alert_trend", "severity", "strength", "segment_volume", "segment_region"]


def monthly_frames(sd: SellerData, cfg: PeerConfig, chosen: dict, base: DetectionParams, cache: dict) -> pd.DataFrame:
    """Historique mensuel par vendeur × indicateur (tous les mois de décision), avec les alertes FINALES de chaque famille.
    Chaque ligne du mois M n'utilise que ce qui était connu à la fin de M."""
    parts = [month_frame(sd, m, metric, cfg, base, cache)[0] for m in ALL_DECISION_MONTHS for metric in METRICS if sd.available[metric]]
    F = pd.concat([p_ for p_ in parts if len(p_)]).reset_index()
    out = None
    for fam, c in chosen.items():
        G = apply_gate(F, c["min_history"], base.min_recent)
        a, ap_ = family_alerts(G, c)
        F[f"alert_{fam}"] = (ap_ if c.get("persistence") else a).to_numpy()
        if fam == "level":
            prev = previous_alerts(G, a)
            F["level_q"], F["eligible"] = G["level_q"].to_numpy(), G["eligible"].to_numpy()
            F["severity"] = [severity(q, p_) if al else None for q, p_, al in zip(G["level_q"], prev, F["alert_level"])]
            F["strength"] = strengths(G).to_numpy()
        else:
            F["eligible_trend"] = G[gate_of(c["detector"], G)].to_numpy()
        out = F
    return out[HISTORY_COLUMNS]


def alert_history(H: pd.DataFrame, chosen: dict) -> pd.DataFrame:
    rows = []
    for fam, c in chosen.items():
        col = f"alert_{fam}"
        base_col = "p_peer" if fam == "level" else "p_hist"
        prev: dict = {}
        for (m, metric), g in H.sort_values("month").groupby(["month", "metric"], sort=True):
            now = set(g.loc[g[col], "seller_id"])
            before = prev.get(metric, set())
            for r in g[g[col] | g["seller_id"].isin(before)].itertuples():
                s_ = r.seller_id
                status = ("ongoing" if s_ in before else "new") if s_ in now else "resolved"
                rows.append({"month": m, "decision_date": str(decision_date(m).date()), "seller_id": s_, "metric": metric, "family": fam,
                             "detector": c["detector"], "status": status, "severity": r.severity if fam == "level" and s_ in now else None,
                             "recent_rate": None if pd.isna(r.rec_rate) else round(float(r.rec_rate), 4), "recent_known_n": int(r.rec_n),
                             "baseline": round(float(getattr(r, base_col)), 4),
                             "eligible": bool(r.eligible if fam == "level" else r.eligible_trend),
                             "params": json.dumps({**c["params"], "min_history": c["min_history"], "persistence": c.get("persistence", False)})})
            prev[metric] = now
    cols = ["month", "decision_date", "seller_id", "metric", "family", "detector", "status", "severity", "recent_rate", "recent_known_n", "baseline",
            "eligible", "params"]
    return pd.DataFrame(rows, columns=cols).sort_values(["month", "metric", "family", "seller_id"]).reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    ap.add_argument("--fast", action="store_true", help="grilles réduites (essais rapides)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--inject-sellers", type=int, default=25)
    a = ap.parse_args()
    p = a.project_dir
    t0 = time.time()
    store = DataStore(p)
    expected, exp_meta = fit_expected(p, store)
    out_model = p / "data/model"
    (out_model / "artifacts").mkdir(parents=True, exist_ok=True)
    if len(expected):
        expected.to_csv(out_model / "bo3_expected.csv.gz", index=False, compression="gzip")
    sd = SellerData(store.orders, expected if len(expected) else None)
    base = DetectionParams()
    cache: dict = {}

    configs = [PeerConfig("global"), PeerConfig("category"), PeerConfig("knn", k=20), PeerConfig("cluster", n_clusters=8)]
    if not a.fast:
        configs += [PeerConfig("knn", k=10), PeerConfig("knn", k=40), PeerConfig("cluster", n_clusters=5), PeerConfig("cluster", n_clusters=12)]
    best_cfg, peers_res = ds31(sd, configs, cache)
    print(f"[DS3.1] référence retenue : {best_cfg.key} ({time.time() - t0:.0f} s)")

    months = [m for m in ALL_DECISION_MONTHS if m <= SPLIT_MONTHS["test"][-1]]
    F = pd.concat([month_frame(sd, m, metric, best_cfg, base, cache)[0] for m in months for metric in METRICS if sd.available[metric]]).reset_index()
    mh_grid = [20, 30, 50] if a.fast else [30, 50, 80]
    det_res, chosen, gated = tune_detectors(F, mh_grid, base.min_recent)
    pers = persistence_eval(gated, chosen)
    sev = severity_eval(gated, chosen)
    stren = strengths_eval(gated, chosen)
    seg = segmentation_eval(F, base.prior_strength)
    print(f"[DS3.2] niveau : {chosen['level']} ; tendance : {chosen['trend']} ({time.time() - t0:.0f} s)")

    inj = injection_benchmark(sd, best_cfg, chosen, base, a.seed, a.inject_sellers)
    print(f"[injection] terminé ({time.time() - t0:.0f} s)")
    H = monthly_frames(sd, best_cfg, chosen, base, cache)
    H.to_csv(out_model / "bo3_monthly_history.csv.gz", index=False, compression="gzip")
    hist = alert_history(H, chosen)
    (p / "data/gold").mkdir(parents=True, exist_ok=True)
    hist.to_csv(p / "data/gold/seller_alert_history.csv", index=False)

    def final_test(fam: str) -> dict:
        return pers[fam]["persistent" if chosen[fam]["persistence"] else "base"]["test"]

    GL = gated[chosen["level"]["min_history"]]
    eligible_per_month = {m: int(GL.loc[(GL["month"] == m) & (GL["metric"] == "late"), "eligible"].sum()) for m in months}
    results = {"protocol": "docs/ShopInsight_Dossier_Technique.pdf, annexe A", "ds3_1_peer_groups": peers_res, "ds3_2_detectors": det_res, "selected": chosen,
               "persistence": pers, "severity": sev, "strengths": stren, "segmentation": seg, "injection_test": inj,
               "eligible_sellers_per_month": eligible_per_month,
               "alert_history": {"rows": int(len(hist)), "by_status": hist["status"].value_counts().to_dict() if len(hist) else {},
                                 "file": "data/gold/seller_alert_history.csv"},
               "monthly_history": {"rows": int(len(H)), "file": "data/model/bo3_monthly_history.csv.gz"},
               "selection_rule": f"par détecteur : meilleur F1 moyen sur les 3 plis VALID parmi les réglages alertant au plus "
                                 f"{int(MAX_ALERT_SHARE * 100)} % des cas éligibles dans CHAQUE pli ; même règle pour la famille et la persistance",
               "truth_definition": "prospective : sur les achats des 60 jours suivant T (issues finales, ≥ 5 commandes), taux significativement supérieur "
                                   "(binomial unilatéral, p < 0,05) à la référence (« niveau ») ou à l'historique rétréci du vendeur (« tendance »)",
               "runtime_seconds": round(time.time() - t0, 1)}
    card = {"created": pd.Timestamp.now().isoformat(timespec="seconds"), "git_commit": git_commit(p),
            "data_sha256": {"orders_analysis": sha256(p / "data/silver/orders_analysis.csv.gz")},
            "peer_config": best_cfg.to_dict(), "peer_label": best_cfg.label, "detection": chosen,
            "severity_rule": SEVERITY_RULE, "strength_alpha": stren["alpha"],
            "min_recent": base.min_recent, "prior_strength": base.prior_strength,
            "windows_days": {"recent": 90, "history": 365, "long_history": 540, "future_for_evaluation_only": 60},
            "validation": {"folds": VALID_FOLDS, "test": SPLIT_MONTHS["test"]},
            "expected_model": exp_meta, "metrics_available": sd.available,
            "test_summary": {fam: {k: final_test(fam).get(k) for k in ("precision", "recall", "f1", "alerts_per_month", "lift")} for fam in chosen},
            "results_file": "quality/bo3_model_results.json"}
    (out_model / "artifacts/bo3_model_card.json").write_text(json.dumps(card, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (p / "quality").mkdir(exist_ok=True)
    (p / "quality/bo3_model_results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(card["test_summary"], indent=2, ensure_ascii=False))
    print(f"terminé en {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
