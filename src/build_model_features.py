"""REHEARSE — préparation des données pour la modélisation (DS1.1 retard, DS1.2 mauvaise note).

Entrées  : data/silver/orders_model_base.csv.gz, orders_analysis.csv.gz, geo_zip_centroid.csv.gz, data/raw (vendeurs, articles)
Sorties  : data/model/features_{train,valid,test}.csv.gz, quality/missing_outliers_report.json, quality/encoding_spec.json

Règles :
- Uniquement des informations connues à l'approbation de la commande.
  Ajout justifié : la date de livraison PROMISE est affichée au client à l'achat → `promised_days` est légitime.
- Découpage chronologique (jamais aléatoire) : train < 2018-01, valid 2018-01..03, test 2018-04..08.
  Les mois incomplets (moins de 100 commandes) sont exclus.
- Valeurs manquantes : imputation par la médiane du TRAIN (par catégorie quand c'est pertinent) + indicateur `<col>_missing`.
- Valeurs aberrantes : jamais supprimées. Variables très asymétriques → log1p puis plafonnement aux quantiles 0,5 % / 99,5 % du TRAIN.
- Encodage : one-hot pour les faibles cardinalités ; encodage par la cible lissé, appris sur le TRAIN seul,
  pour la catégorie (74 valeurs) et le vendeur (~3 000 valeurs) ; vendeur inconnu → moyenne globale.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

TRAIN_END, VALID_END, TEST_END = "2018-01-01", "2018-04-01", "2018-09-01"
SKEWED = ["item_price_total", "freight_total", "payment_total", "product_weight_mean_g", "product_volume_mean_cm3", "approval_delay_hours", "distance_km"]


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def target_encode(train_key, train_y, keys, prior, smoothing=20):
    stats = pd.DataFrame({"k": train_key.values, "y": train_y.values}).groupby("k")["y"].agg(["sum", "count"])
    enc = (stats["sum"] + prior * smoothing) / (stats["count"] + smoothing)
    return keys.map(enc).fillna(prior).astype(float), int(len(stats))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    p = ap.parse_args().project_dir.resolve()
    silver, raw, out = p / "data/silver", p / "data/raw", p / "data/model"
    out.mkdir(parents=True, exist_ok=True)

    m = pd.read_csv(silver / "orders_model_base.csv.gz", low_memory=False, parse_dates=["order_purchase_timestamp", "order_approved_at"],
                    dtype={"customer_zip_code_prefix": "string"})
    a = pd.read_csv(silver / "orders_analysis.csv.gz", low_memory=False, usecols=["order_id", "order_estimated_delivery_date"],
                    parse_dates=["order_estimated_delivery_date"])
    geo = pd.read_csv(silver / "geo_zip_centroid.csv.gz", dtype={"geolocation_zip_code_prefix": "string"})
    sellers = pd.read_csv(raw / "olist_sellers_dataset.csv", dtype={"seller_zip_code_prefix": "string"})
    items = pd.read_csv(raw / "olist_order_items_dataset.csv", usecols=["order_id", "order_item_id", "seller_id"])

    # --- Features connues à l'achat -----------------------------------------
    m = m.merge(a, on="order_id", how="left", validate="one_to_one")
    m["promised_days"] = (m["order_estimated_delivery_date"].dt.normalize() - m["order_purchase_timestamp"].dt.normalize()).dt.days
    m = m.drop(columns=["order_estimated_delivery_date"])
    m["purchase_month_num"] = m["order_purchase_timestamp"].dt.month
    m["is_weekend"] = m["purchase_weekday"].isin([5, 6]).astype(int)
    # vendeur principal = vendeur du premier article (unique vendeur dans 98,7 % des commandes)
    main_seller = items.sort_values("order_item_id").drop_duplicates("order_id")[["order_id", "seller_id"]]
    m = m.merge(main_seller, on="order_id", how="left", validate="one_to_one")
    sg = sellers.merge(geo[geo["is_within_brazil"]][["geolocation_zip_code_prefix", "latitude", "longitude"]],
                       left_on="seller_zip_code_prefix", right_on="geolocation_zip_code_prefix", how="left")
    m = m.merge(sg[["seller_id", "seller_state", "latitude", "longitude"]].rename(columns={"latitude": "seller_lat", "longitude": "seller_lng"}),
                on="seller_id", how="left")
    m["distance_km"] = haversine(m["customer_lat"], m["customer_lng"], m["seller_lat"], m["seller_lng"])
    m["same_state"] = (m["customer_state"] == m["seller_state"]).astype(int)

    # --- Découpage chronologique, mois incomplets exclus --------------------
    counts = m["purchase_month"].value_counts()
    complete = counts[counts >= 100].index
    m = m[m["purchase_month"].isin(complete)].copy()
    t = m["order_purchase_timestamp"]
    m["split"] = np.select([t < TRAIN_END, t < VALID_END, t < TEST_END], ["train", "valid", "test"], "drop")
    m = m[m["split"] != "drop"].copy()
    tr = m["split"] == "train"

    # --- Audit des valeurs manquantes (avant traitement) --------------------
    feat_raw = ["approval_delay_hours", "product_weight_mean_g", "product_volume_mean_cm3", "payment_total", "payment_installments_max",
                "distance_km", "promised_days", "item_price_total", "freight_total"]
    missing = {c: int(m[c].isna().sum()) for c in feat_raw}

    # --- Valeurs aberrantes : audit IQR + traitement ------------------------
    outliers = {}
    for c in SKEWED:
        q1, q3 = m.loc[tr, c].quantile([.25, .75])
        hi = q3 + 3 * (q3 - q1)
        outliers[c] = {"extreme_above_Q3+3IQR": int((m[c] > hi).sum()), "max": float(np.nanmax(m[c])), "median": float(np.nanmedian(m[c]))}
    negative_promise = int((m["promised_days"] <= 0).sum())

    # --- Imputation (médianes du TRAIN) + indicateurs ------------------------
    for c in ["product_weight_mean_g", "product_volume_mean_cm3"]:
        m[f"{c}_missing"] = m[c].isna().astype(int)
        cat_med = m[tr].groupby("primary_category")[c].median()
        m[c] = m[c].fillna(m["primary_category"].map(cat_med)).fillna(m.loc[tr, c].median())
    for c in ["approval_delay_hours", "payment_total", "payment_installments_max", "distance_km", "item_price_total", "freight_total"]:
        m[f"{c}_missing"] = m[c].isna().astype(int)
        m[c] = m[c].fillna(m.loc[tr, c].median())

    # --- log1p + plafonnement (quantiles du TRAIN) ---------------------------
    caps = {}
    for c in SKEWED:
        x = np.log1p(m[c].clip(lower=0))
        lo, hi = x[tr].quantile([.005, .995])
        m[f"{c}_log"] = x.clip(lo, hi)
        caps[c] = [float(lo), float(hi)]
    m["promised_days"] = m["promised_days"].clip(1, m.loc[tr, "promised_days"].quantile(.995))

    # --- Encodage ------------------------------------------------------------
    m["customer_state"] = m["customer_state"].fillna("unknown")
    state_d = pd.get_dummies(m["customer_state"], prefix="state", dtype=int)
    m = pd.concat([m, state_d], axis=1)
    enc_info = {}
    for target in ["is_late", "is_poor_review"]:
        lab = tr & m[target].notna()
        prior = float(m.loc[lab, target].mean())
        short = "late" if target == "is_late" else "poor"
        m["seller_state"] = m["seller_state"].fillna("unknown")
        counts_seen = []
        for col, name in [("primary_category", "category"), ("seller_id", "seller"), ("seller_state", "sellerstate")]:
            # valid/test : encodage appris sur tout le TRAIN étiqueté
            enc, n = target_encode(m.loc[lab, col], m.loc[lab, target], m[col], prior)
            # train : encodage hors-pli (5 plis) pour que la ligne ne voie pas sa propre cible
            idx = np.where(tr.values)[0]
            folds = np.arange(len(idx)) % 5
            np.random.default_rng(42).shuffle(folds)
            for f in range(5):
                fit_rows = m.index[idx[folds != f]]
                fit_rows = fit_rows[m.loc[fit_rows, target].notna()]
                apply_rows = m.index[idx[folds == f]]
                enc.loc[apply_rows], _ = target_encode(m.loc[fit_rows, col], m.loc[fit_rows, target], m.loc[apply_rows, col], prior)
            m[f"te_{name}_{short}"] = enc
            counts_seen.append(n)
        n1, n2, n3 = counts_seen
        enc_info[target] = {"prior": prior, "categories_seen": n1, "sellers_seen": n2, "seller_states_seen": n3, "smoothing": 20}
    seller_train_counts = m[tr].groupby("seller_id").size()
    m["seller_train_orders_log"] = np.log1p(m["seller_id"].map(seller_train_counts).fillna(0))

    features = (["promised_days", "purchase_weekday", "purchase_hour", "purchase_month_num", "is_weekend", "item_count", "product_count",
                 "seller_count", "payment_rows", "payment_type_count", "payment_installments_max", "same_state", "seller_train_orders_log"]
                + [f"{c}_log" for c in SKEWED]
                + [c for c in m.columns if c.endswith("_missing")]
                + list(state_d.columns)
                + [c for c in m.columns if c.startswith("te_")])
    keep = ["order_id", "order_purchase_timestamp", "split", "late_label_eligible", "is_late", "poor_review_label_eligible", "is_poor_review"] + features
    for s in ["train", "valid", "test"]:
        m.loc[m["split"] == s, keep].to_csv(out / f"features_{s}.csv.gz", index=False, compression="gzip")

    split_info = {s: {"orders": int((m["split"] == s).sum()),
                      "late_labelled": int(((m["split"] == s) & m["late_label_eligible"]).sum()),
                      "late_rate": round(float(m.loc[(m["split"] == s) & m["late_label_eligible"], "is_late"].mean()), 4),
                      "poor_labelled": int(((m["split"] == s) & m["poor_review_label_eligible"]).sum()),
                      "poor_rate": round(float(m.loc[(m["split"] == s) & m["poor_review_label_eligible"], "is_poor_review"].mean()), 4)}
                  for s in ["train", "valid", "test"]}
    report = {"missing_before_imputation": missing, "outliers_iqr3_train_fences": outliers, "nonpositive_promised_days": negative_promise,
              "log_caps": caps, "splits": split_info, "n_features": len(features)}
    (p / "quality/missing_outliers_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (p / "quality/encoding_spec.json").write_text(json.dumps({"features": features, "target_encoding": enc_info,
        "one_hot": {"customer_state": list(state_d.columns)}, "split_bounds": [TRAIN_END, VALID_END, TEST_END]}, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
