"""REHEARSE — BO3 : panel vendeurs « à date » (fondation sans fuite temporelle).

Une ligne par (mois de décision M, vendeur, indicateur) : décision prise à T = début du mois M+1.
  - comptages récents (achats des 90 jours avant T) et historiques (achats de T-365 à T-90 jours), issues CONNUES avant T uniquement ;
  - profil du vendeur sur les 12 mois avant T (catégories, destinations, volume, prix, port, poids, délai promis) : aucune issue utilisée ;
  - colonnes eval_* : issues finales des achats des 60 jours SUIVANT T — réservées à l'évaluation, jamais à une décision.
Pourquoi pas seller_monthly_kpis ? Cette table regroupe par mois d'achat avec les issues finales : la ligne du mois M contient des
livraisons et des avis survenus des semaines après M. Elle reste valable pour la description, pas pour décider à T.

Sortie : data/model/seller_panel_asof.csv.gz
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents.bo3_sellers import ALL_DECISION_MONTHS, METRICS, SellerData, decision_date, split_of  # noqa: E402
from agents.core import DataStore  # noqa: E402


def build_panel(sd: SellerData, months: list[str]) -> pd.DataFrame:
    parts = []
    for m in months:
        T = decision_date(m)
        prof = sd.profile(T)
        if prof.empty:
            continue
        keep = [c for c in prof.columns if c not in ("first_order", "last_order")]
        for metric in METRICS:
            if not sd.available[metric]:
                continue
            c = sd.counts(T, metric).reindex(prof.index).fillna(0)
            c = c[[x for x in c.columns if not x.startswith("rec_e") and x not in ("rec_ne", "rec_xe", "rec_v")]]
            c = c.rename(columns={"fut_n": "eval_future_n", "fut_x": "eval_future_events"})
            parts.append(pd.concat([c, prof[keep]], axis=1).assign(month=m, decision_date=T.date().isoformat(), split=split_of(m), metric=metric))
    panel = pd.concat(parts).rename_axis("seller_id").reset_index()
    first = ["month", "decision_date", "split", "seller_id", "metric", "rec_n", "rec_x", "hist_n", "hist_x", "year_n", "year_x",
             "n_orders_recent", "n_orders_year", "eval_future_n", "eval_future_events"]
    return panel[first + [c for c in panel.columns if c not in first]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    a = ap.parse_args()
    sd = SellerData(DataStore(a.project_dir).orders)
    panel = build_panel(sd, ALL_DECISION_MONTHS)
    out = a.project_dir / "data/model/seller_panel_asof.csv.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out, index=False, compression="gzip")
    print(f"{len(panel)} lignes ({panel['seller_id'].nunique()} vendeurs, {panel['month'].nunique()} mois de décision) -> {out}")


if __name__ == "__main__":
    main()
