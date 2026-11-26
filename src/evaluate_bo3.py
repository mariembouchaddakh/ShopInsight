"""Évaluation de l'agent BO3 (DS3.3) — fichier propre à BO3 ; evaluate_agents.py (BO1/BO2) n'est pas modifié.

Audits vendeur aux décisions TEST (avr.–juin 2018), échantillon stratifié : en alerte / éligibles sans alerte / petit volume.
  C1 structure complète                              C2 toute ligne citée → preuves existantes
  C3 aucune information postérieure à la décision : le même audit relancé sur des données AMPUTÉES de tout ce qui suit T
     (achats après T, livraisons / remises / avis survenus après T) donne exactement les mêmes chiffres et alertes
  C4 vendeurs comparables identiques sur données amputées, tous actifs avant T
  C5 taux récent = recalcul indépendant ; résumé vérifié   C6 aucun langage causal   C7 tout taux est accompagné de son effectif
Sortie : quality/bo3_agent_evaluation.json
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
from agents.bo3_agent import SellerAuditAgent  # noqa: E402
from agents.bo3_sellers import SPLIT_MONTHS, decision_date  # noqa: E402
from agents.bo3_support import verify_bo3_narrative  # noqa: E402
from evaluate_agents import CAUSAL, agent_text, all_lines  # noqa: E402  (lecture seule : mêmes règles que BO1/BO2)

COUNT = re.compile(r"n = \d+|\d+ commandes|\d+ avis|\d+ issues")


def truncate_orders(o: pd.DataFrame, T: pd.Timestamp) -> pd.DataFrame:
    """Données telles qu'on les aurait eues à T — réécriture INDÉPENDANTE de la règle de bo3_sellers :
    on supprime les achats ≥ T et on efface toute date / issue survenue après T."""
    o = o[o["order_purchase_timestamp"] < T].copy()
    for c in ("order_delivered_carrier_date", "shipping_limit_max"):
        if c in o.columns:
            o[c] = pd.to_datetime(o[c], errors="coerce", format="mixed")
    day = pd.Timedelta(days=1)
    dlv, est = o["order_delivered_customer_date"], o["order_estimated_delivery_date"]
    late_known = (dlv.notna() & (dlv <= T)) | (est.dt.normalize() + day <= T)
    o.loc[~late_known, "is_late"] = np.nan
    o.loc[dlv.notna() & (dlv > T), "order_delivered_customer_date"] = pd.NaT
    if "late_days" in o.columns:
        o.loc[o["order_delivered_customer_date"].isna(), "late_days"] = np.nan
    ans = o["review_answer_timestamp"]
    rv = ans.notna() & (ans <= T)
    o.loc[~rv, ["is_poor_review", "review_score"]] = np.nan
    o.loc[~rv, "review_answer_timestamp"] = pd.NaT
    if "is_late_handover" in o.columns:
        car, lim = o["order_delivered_carrier_date"], o["shipping_limit_max"]
        h_known = (car.notna() & (car <= T)) | (lim.dt.normalize() + day <= T)
        o.loc[~h_known, "is_late_handover"] = np.nan
        o.loc[car.notna() & (car > T), "order_delivered_carrier_date"] = pd.NaT
        o.loc[o["order_delivered_carrier_date"].isna(), "handover_delay_days"] = np.nan
    return o


def _close(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a))
    return a == b


def eval_bo3(project: Path, n_per_group: int, seed: int) -> dict:
    ag = SellerAuditAgent(project)
    rng = np.random.default_rng(seed)
    o_full = ag.store.orders
    months = SPLIT_MONTHS["test"]
    groups: dict[str, list] = {"en_alerte": [], "eligible_sans_alerte": [], "petit_volume": []}
    c = ag.card["detection"]
    for m in months:
        gated, _ = ag._frame(m, "late")
        L, Tr = gated["level"], gated["trend"]
        st = ag._alert_state(m, "late")  # alertes finales de l'agent (règle de persistance comprise)
        on = set(st["level"].index[st["level"]["final"]]) | set(st["trend"].index[st["trend"]["final"]])
        groups["en_alerte"] += [(s_, m) for s_ in sorted(on)]
        groups["eligible_sans_alerte"] += [(s_, m) for s_ in sorted(set(L.index[L["eligible"]]) - on)]
        groups["petit_volume"] += [(s_, m) for s_ in sorted(set(L.index[~L["eligible"]]))]
    cases = []
    for g, pool in groups.items():
        if pool:
            idx = rng.choice(len(pool), min(n_per_group, len(pool)), replace=False)
            cases += [(pool[i][0], pool[i][1], g) for i in sorted(idx)]
    keys = ("C1_structure", "C2_citations", "C3_pas_d_information_future", "C4_pairs_passes", "C5_chiffres_exacts",
            "C6_pas_de_causalite", "C7_effectifs_affiches")
    checks = {k: 0 for k in keys}
    failures, trunc = [], {}
    first_order = o_full.groupby("single_seller_id")["order_purchase_timestamp"].min()
    for sid, m, g in cases:
        T = decision_date(m)
        rep = ag.audit(sid, m, use_llm=False)
        log = ag.log
        lines = all_lines(rep)
        ok1 = bool(rep.facts and rep.estimates and rep.actions and rep.caveats)
        ok2 = all(e in log.ids() for l in lines for e in l.evidence)
        if m not in trunc:
            tr_orders = truncate_orders(o_full, T)
            trunc[m] = (SellerAuditAgent(project, orders=tr_orders), tr_orders)
        tg, tr_orders = trunc[m]
        ok3, ok4 = True, True
        for met in ag.metrics:
            a1 = log.get(f"kpi:seller:{sid[:8]}:{m}:{met}")
            d0 = log.get(f"alr:{sid[:8]}:{m}:{met}")
            if a1 is None or d0 is None:
                continue
            try:
                b1 = tg.compare_to_peers(sid, m, met)["observed"]
                d1 = tg.detect_deterioration(sid, m, met)
            except KeyError:
                ok3 = False
                continue
            ok3 &= _close(to_plain(a1.payload), b1)
            ok3 &= all(d0.payload["families"][f]["alert"] == d1["families"][f]["alert"]
                       and _close(to_plain(d0.payload["families"][f]["raw"]), d1["families"][f]["raw"]) for f in d0.payload["families"])
        p0 = log.get(f"peer:{sid[:8]}:{m}")
        if p0 is not None:
            p1 = tg.get_peer_group(sid, m)
            ok4 = [x["seller_id"] for x in p0.payload["peers"]] == [x["seller_id"] for x in p1["peers"]]
            ok4 &= all(first_order.get(x["seller_id"], T) < T for x in p0.payload["peers"])
        # C5 : recalcul indépendant du taux récent de retard (mono-vendeur, achats [T-90 j, T), issue connue à T) + résumé vérifié
        ok5 = verify_bo3_narrative(rep.narrative, log)[0]
        k = log.get(f"kpi:seller:{sid[:8]}:{m}:late")
        if k is not None:
            sub = tr_orders[(tr_orders["single_seller_id"] == sid) & (tr_orders["order_purchase_timestamp"] >= T - pd.Timedelta(days=90))
                            & tr_orders["late_label_eligible"].astype(bool) & tr_orders["is_late"].notna()]
            if "seller_count" in sub.columns:
                sub = sub[pd.to_numeric(sub["seller_count"], errors="coerce").fillna(1).eq(1)]
            ok5 &= int(len(sub)) == k.payload["recent_known_n"] and int(sub["is_late"].astype(float).sum()) == k.payload["recent_events"]
        ok6 = not any(CAUSAL.search(agent_text(l.text)) for l in lines) and not CAUSAL.search(agent_text(rep.narrative))
        ok7 = all(COUNT.search(l.text) for l in rep.facts + rep.estimates if "%" in l.text)
        for key, ok in zip(keys, (ok1, ok2, ok3, ok4, ok5, ok6, ok7)):
            checks[key] += int(bool(ok))
            if not ok:
                failures.append({"seller_id": sid, "month": m, "group": g, "check": key})
    n = len(cases)
    mr = project / "quality/bo3_model_results.json"
    models = json.loads(mr.read_text(encoding="utf-8")) if mr.exists() else None
    return {"n_cases": n, "cases_by_group": {g: sum(1 for x in cases if x[2] == g) for g in groups},
            "checks_passed": {k: f"{v}/{n}" for k, v in checks.items()}, "success_rate": sum(checks.values()) / max(1, n * len(checks)),
            "failures": failures[:15],
            "model_summary": None if models is None else {
                "selected": models["selected"],
                "test": {fam: models["ds3_2_detectors"][d["detector"]]["test"] for fam, d in models["selected"].items()}}}


def to_plain(x):
    return json.loads(json.dumps(x, default=str))



def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    ap.add_argument("--n-per-group", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    res = eval_bo3(a.project_dir, a.n_per_group, a.seed)
    out = a.project_dir / "quality/bo3_agent_evaluation.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"n_cases": res["n_cases"], "checks_passed": res["checks_passed"], "failures": res["failures"]}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
