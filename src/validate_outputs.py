"""Validation indépendante des sorties de la phase 2.

Relit uniquement les fichiers produits (et les CSV bruts), sans importer prepare_data.py,
et recalcule les règles de préparation à partir de zéro.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", required=True, type=Path)
    p = parser.parse_args().project_dir
    raw, silver, gold = p / "data" / "raw", p / "data" / "silver", p / "data" / "gold"

    orders = pd.read_csv(raw / "olist_orders_dataset.csv")
    items = pd.read_csv(raw / "olist_order_items_dataset.csv")
    reviews = pd.read_csv(raw / "olist_order_reviews_dataset.csv")
    a = pd.read_csv(silver / "orders_analysis.csv.gz", low_memory=False)
    m = pd.read_csv(silver / "orders_model_base.csv.gz", low_memory=False)
    links = pd.read_csv(silver / "multi_seller_order_links.csv.gz")
    seller = pd.read_csv(silver / "seller_monthly_kpis.csv.gz")
    geo = pd.read_csv(silver / "geo_zip_centroid.csv.gz")
    monthly = pd.read_csv(gold / "monthly_business_kpis.csv")
    state = pd.read_csv(gold / "state_monthly_kpis.csv.gz")
    category = pd.read_csv(gold / "category_monthly_kpis.csv.gz")
    with gzip.open(silver / "reviews_text.jsonl.gz", "rt", encoding="utf-8") as stream:
        docs = [json.loads(line) for line in stream]

    for c in ["order_approved_at", "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date", "order_purchase_timestamp"]:
        orders[c] = pd.to_datetime(orders[c])

    # Recalculs à partir des fichiers bruts
    delivered = orders["order_status"].eq("delivered") & orders["order_delivered_customer_date"].notna()
    late = (
        orders.loc[delivered, "order_delivered_customer_date"].dt.normalize()
        > orders.loc[delivered, "order_estimated_delivery_date"].dt.normalize()
    )
    sellers_per_order = items.groupby("order_id")["seller_id"].nunique()
    multi_ids = set(sellers_per_order[sellers_per_order > 1].index)
    no_item_ids = set(orders["order_id"]) - set(items["order_id"])
    msg = reviews["review_comment_message"].fillna("").str.strip().ne("")
    title = reviews["review_comment_title"].fillna("").str.strip().ne("")
    counts = orders["order_purchase_timestamp"].dt.to_period("M").astype(str).value_counts()

    forbidden = [
        c for c in m.columns
        if any(k in c for k in ["delivered", "estimated", "status", "review_score", "review_comment", "late_days", "duration", "carrier", "flag_"])
    ]

    results = {
        "orders_unique": bool(a["order_id"].is_unique and len(a) == len(orders)),
        "late_recomputed_matches": int(a["is_late"].sum()) == int(late.sum()) and int(a["late_label_eligible"].sum()) == int(delivered.sum()),
        "duration_only_for_delivered": int(a["delivery_duration_days"].notna().sum()) == int(delivered.sum()),
        "no_items_label_matches_raw": set(a.loc[a["primary_category"].eq("no_items"), "order_id"]) == no_item_ids,
        "unknown_label_only_with_items": bool(a.loc[a["primary_category"].eq("unknown"), "item_count"].gt(0).all()),
        "multi_seller_flag_matches_raw": set(a.loc[a["is_multi_seller"], "order_id"]) == multi_ids,
        "multi_seller_links_rows_match_raw": len(links) == int(items[items["order_id"].isin(multi_ids)].groupby(["order_id", "seller_id"]).ngroups),
        "seller_kpis_contain_no_multi_seller_order": int(seller["order_count"].sum()) == int((sellers_per_order == 1).sum()),
        "jsonl_message_docs_match_raw": sum(d["has_message"] for d in docs) == int(msg.sum()),
        "jsonl_all_text_docs_match_raw": len(docs) == int((msg | title).sum()),
        "model_base_has_no_future_columns": forbidden == [],
        "monthly_months_contiguous": list(monthly["purchase_month"]) == list(
            pd.period_range(monthly["purchase_month"].min(), monthly["purchase_month"].max(), freq="M").astype(str)
        ),
        "sparse_flag_matches_raw_counts": all(
            row.is_complete_period == (counts.get(row.purchase_month, 0) >= 100) for row in monthly.itertuples()
        ),
        "period_flag_present_in_all_kpi_tables": all("is_complete_period" in t.columns and t["is_complete_period"].notna().all() for t in [monthly, state, category, seller]),
        "date_flags_recomputed_match": int(a["flag_carrier_before_approval"].sum()) == int((orders["order_delivered_carrier_date"] < orders["order_approved_at"]).sum())
        and int(a["flag_delivered_before_carrier"].sum()) == int((orders["order_delivered_customer_date"] < orders["order_delivered_carrier_date"]).sum()),
        "geo_centroids_inside_brazil": bool(
            geo.loc[geo["is_within_brazil"], "latitude"].between(-33.8, 5.3).all()
            and geo.loc[geo["is_within_brazil"], "longitude"].between(-74.0, -34.7).all()
        ),
    }
    summary = {
        "checks": results,
        "passed": all(results.values()),
        "figures": {
            "orders": int(len(a)),
            "late_eligible": int(delivered.sum()),
            "late_orders": int(late.sum()),
            "multi_seller_orders": len(multi_ids),
            "orders_without_items": len(no_item_ids),
            "review_documents_all_text": len(docs),
            "review_documents_with_message": int(msg.sum()),
            "incomplete_months": monthly.loc[~monthly["is_complete_period"], "purchase_month"].tolist(),
            "orders_with_date_issue": int(a["flag_any_date_issue"].sum()),
        },
    }
    (p / "quality" / "independent_validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
