"""Évaluation des agents BO1 et BO2 sur des scénarios fixes (exigence du plan : « task success, cited facts »).

BO1 (commandes de la période TEST, avr.–août 2018, échantillon stratifié par tranche de risque) :
  C1 structure complète (faits, estimations, actions, limites)       C2 toute ligne citée → preuves existantes
  C3 aucune fuite de l'issue réelle hors mode audit                   C4 commandes comparables : issue connue AVANT l'achat cible
  C5 chiffres du modèle = recalcul indépendant ; résumé vérifié       C6 aucun langage causal affirmé
  + utilité : capture du top 10 % par mois (rappel, précision, gain vs hasard).
BO2 :
  - alertes « livraison » rétrospectives vs un proxy indépendant des données : mois où le taux de retard (gold) dépasse 1,5 × la médiane des 3 mois précédents et 8 % ;
  - contrôles structurels des rapports (citations d'avis réelles, extraits ≤ 260 caractères, traduction signalée, résumé vérifié) ;
  - F1 par aspect si quality/annotated_reviews.csv existe ; sinon génère quality/annotation_template.csv (500 avis stratifiés à annoter).
Sortie : quality/agent_evaluation.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents.bo1_agent import PreventiveDiagnosisAgent  # noqa: E402
from agents.bo2_agent import VoiceOfCustomerAgent  # noqa: E402
from agents.bo2_nlp import ASPECTS, emerging_aspects  # noqa: E402
from agents.core import verify_narrative  # noqa: E402

CAUSAL = re.compile(r"\b(à cause de|causé par|a causé|parce que|c'est dû à)\b", re.I)
QUOTE = re.compile(r"«[^»]*»")  # les propos cités d'un client ne sont pas des affirmations de l'agent


def agent_text(t: str) -> str:
    return QUOTE.sub(" ", t)


def all_lines(rep):
    return rep.facts + rep.estimates + rep.similar + rep.actions


def eval_bo1(project: Path, n_per_band: int, seed: int) -> dict:
    ag = PreventiveDiagnosisAgent(project)
    rng = np.random.default_rng(seed)
    test = ag.store.features("test")
    sc = ag._score("late", test[ag.bundles["late"]["features"]].astype(float).values)
    pc = ag._percentile("late", sc)
    band = np.where(pc >= .9, "élevé", np.where(pc >= .7, "modéré", "faible"))
    ids = []
    for b in ("élevé", "modéré", "faible"):
        pool = test.index[band == b]
        ids += list(test.loc[rng.choice(pool, min(n_per_band, len(pool)), replace=False), "order_id"])
    checks = {k: 0 for k in ("C1_structure", "C2_citations", "C3_pas_de_fuite", "C4_comparables_passes", "C5_chiffres_exacts", "C6_pas_de_causalite")}
    failures = []
    for oid in ids:
        rep = ag.diagnose(oid, audit=False, use_llm=False)
        log = ag.log
        ok1 = bool(rep.facts and rep.estimates and rep.actions and rep.caveats)
        ok2 = all(e in log.ids() for l in all_lines(rep) for e in l.evidence)
        ok3 = log.get(f"ord:{oid}:issue") is None and not any("RÉTROSPECTIF" in l.text for l in all_lines(rep))
        sim = log.get(f"ord:{oid}:similar").payload
        t0 = ag.store.orders.loc[oid, "order_purchase_timestamp"]
        ok4 = all(ag.store.orders.loc[c["order_id"], "order_delivered_customer_date"] <= t0 for c in sim.get("cases", []))
        x = ag.store.all_features.loc[oid, ag.bundles["late"]["features"]].astype(float).values.reshape(1, -1)
        recomputed = float(ag._percentile("late", ag._score("late", x)[0]))
        ok5 = abs(recomputed - log.get(f"mdl:late:{oid}").payload["percentile"]) < 1e-3 and verify_narrative(rep.narrative, log)[0]
        ok6 = not any(CAUSAL.search(agent_text(l.text)) for l in all_lines(rep)) and not CAUSAL.search(agent_text(rep.narrative))
        for k, ok in zip(checks, (ok1, ok2, ok3, ok4, ok5, ok6)):
            checks[k] += int(ok)
            if not ok:
                failures.append({"order_id": oid, "check": k})
    # utilité du tri
    util = []
    for m in sorted(ag.store.features("test")["order_purchase_timestamp"].dt.strftime("%Y-%m").unique()):
        for tgt in ("late", "poor"):
            try:
                p = ag.triage_orders(m, 20, tgt)
            except KeyError:
                continue
            ag.audit = True
            p = ag.triage_orders(m, 20, tgt)
            ag.audit = False
            b = p.get("backtest")
            if b and b["positives"]:
                util.append({"month": m, "target": tgt, "recall_top10": b["captured_in_top10pct"] / b["positives"], "precision_top10": b["precision_top10pct"],
                             "lift_vs_random": b["precision_top10pct"] / b["base_rate"]})
    n = len(ids)
    return {"n_orders": n, "checks_passed": {k: f"{v}/{n}" for k, v in checks.items()}, "success_rate": sum(checks.values()) / (n * len(checks)),
            "failures": failures[:10], "triage_utility": util}


def make_annotation_template(ag: VoiceOfCustomerAgent, out: Path, n: int = 500, seed: int = 42) -> None:
    an = ag.an
    parts = []
    per = max(1, n // 5)
    for s in range(1, 6):
        d = an[an["score"] == s]
        parts.append(d.sample(min(per, len(d)), random_state=seed))
    d = pd.concat(parts)[["review_id", "score", "full_pt", "full_fr"]].rename(columns={"full_pt": "text_pt", "full_fr": "text_fr"})
    for a in ASPECTS:
        d[a] = ""
    d.to_csv(out, index=False, encoding="utf-8-sig")


def f1_per_aspect(ag: VoiceOfCustomerAgent, ann: pd.DataFrame) -> dict:
    # un même avis peut être rattaché à plusieurs commandes : ses prédictions sont identiques, on garde une ligne par avis
    an = ag.an.drop_duplicates("review_id").set_index("review_id")
    res = {}
    ann = ann.drop_duplicates("review_id")
    ann = ann[ann["review_id"].isin(an.index)]
    for a in ASPECTS:
        gold = pd.to_numeric(ann[a], errors="coerce")  # NaN = non mentionné
        pred = an.loc[ann["review_id"], f"a_{a}"].values
        g_neg, p_neg = (gold == -1).values, (pred == -1)
        g_men, p_men = gold.notna().values, ~pd.isna(pred)
        def prf(g, p):
            tp = int((g & p).sum()); fp = int((~g & p).sum()); fn = int((g & ~p).sum())
            pr = tp / (tp + fp) if tp + fp else 0.0; rc = tp / (tp + fn) if tp + fn else 0.0
            return {"precision": round(pr, 3), "recall": round(rc, 3), "f1": round(2 * pr * rc / (pr + rc), 3) if pr + rc else 0.0, "support": int(g.sum())}
        res[a] = {"detection": prf(g_men, p_men), "negative": prf(g_neg, p_neg)}
    return res


def eval_bo2(project: Path) -> dict:
    ag = VoiceOfCustomerAgent(project)
    an, monthly = ag.an, ag.store.monthly.set_index("purchase_month")
    counts = an.groupby("month").size()
    months = [m for m in sorted(counts.index) if counts[m] >= 150]
    rows = []
    for i, m in enumerate(months):
        prev = [x for x in monthly.index if x < m][-3:]
        if len(prev) < 3:
            continue
        lr = monthly.loc[m, "late_rate"]
        med = monthly.loc[prev, "late_rate"].median()
        event = bool(lr >= 1.5 * med and lr >= 0.08)
        res = emerging_aspects(an, m)
        fired = any(a["alert"] and a["aspect"] == "livraison" for a in res["aspects"])
        other = [a["aspect"] for a in res["aspects"] if a["alert"] and a["aspect"] != "livraison"]
        rows.append({"month": m, "late_rate": round(float(lr), 4), "delay_event_proxy": event, "delivery_alert": fired, "other_alerts": other})
    tp = sum(r["delay_event_proxy"] and r["delivery_alert"] for r in rows)
    fp = sum((not r["delay_event_proxy"]) and r["delivery_alert"] for r in rows)
    fn = sum(r["delay_event_proxy"] and not r["delivery_alert"] for r in rows)
    alert_eval = {"months": rows, "alert_precision": tp / (tp + fp) if tp + fp else None, "alert_recall": tp / (tp + fn) if tp + fn else None,
                  "tp": tp, "fp": fp, "fn": fn,
                  "note": "proxy indépendant : taux de retard du mois ≥ 1,5 × médiane des 3 mois précédents et ≥ 8 %"}
    # contrôles structurels
    reviews_ids = set(ag.store.reviews()["review_id"])
    scen = [(m, None, None) for m in months[-6:]] + [(months[-1], s, None) for s in an["state"].value_counts().index[:3]]
    ok = 0
    problems = []
    for m, s, c in scen:
        rep = ag.report(m, s, c, use_llm=False)
        log = ag.log
        cited = all(e in log.ids() for l in all_lines(rep) for e in l.evidence)
        real = all(e.id[4:] in reviews_ids for e in log.with_prefix("rev:"))
        short = all(len(e.payload["excerpt"]) <= 262 for e in log.with_prefix("rev:"))
        mt = all(("traduction automatique" in l.text or "portugais original" in l.text) for l in rep.similar)
        ver = verify_narrative(rep.narrative, log)[0]
        good = cited and real and short and mt and ver and bool(rep.caveats)
        ok += int(good)
        if not good:
            problems.append({"month": m, "state": s, "cited": cited, "real": real, "short": short, "mt": mt, "narrative": ver})
    out = {"alert_backtest": alert_eval, "structure": {"scenarios": len(scen), "passed": ok, "problems": problems}}
    ann_path = project / "quality/annotated_reviews.csv"
    if ann_path.exists():
        out["f1_per_aspect"] = f1_per_aspect(ag, pd.read_csv(ann_path))
    else:
        tpl = project / "quality/annotation_template.csv"
        make_annotation_template(ag, tpl)
        out["f1_per_aspect"] = f"en attente : annotez {tpl.name} (−1 critique, 0 neutre, 1 positif, vide = non mentionné) et renommez-le annotated_reviews.csv"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    ap.add_argument("--n-per-band", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    res = {"bo1": eval_bo1(a.project_dir, a.n_per_band, a.seed), "bo2": eval_bo2(a.project_dir)}
    (a.project_dir / "quality/agent_evaluation.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(res, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
