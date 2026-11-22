from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pandas as pd


DATE_COLUMNS = {
    "olist_orders_dataset.csv": [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ],
    "olist_order_items_dataset.csv": ["shipping_limit_date"],
    "olist_order_reviews_dataset.csv": [
        "review_creation_date",
        "review_answer_timestamp",
    ],
}

SOURCE_FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]


# Un mois d'achat comptant moins de commandes que ce seuil est marqué « partiel ».
# Il reste dans les tables, mais ne doit pas être tracé comme une tendance réelle.
SPARSE_MONTH_MIN_ORDERS = 100

# Emprise approximative du Brésil (points extrêmes du territoire, avec une petite marge).
BRAZIL_BBOX = {"lat_min": -33.8, "lat_max": 5.3, "lng_min": -74.0, "lng_max": -34.7}

# Étiquettes de catégorie distinctes pour ne pas confondre deux situations différentes.
NO_ITEMS_LABEL = "no_items"          # commande sans aucun article
UNKNOWN_CATEGORY_LABEL = "unknown"   # articles présents, mais produit sans catégorie


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path, *, dtype: dict[str, str] | None = None) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=dtype, low_memory=False)
    for column in DATE_COLUMNS.get(path.name, []):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def mode_or_unknown(series: pd.Series) -> str:
    values = series.dropna().astype(str)
    if values.empty:
        return "unknown"
    modes = values.mode()
    return str(modes.iloc[0]) if not modes.empty else str(values.iloc[0])


def safe_rate(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = numerator / denominator.replace(0, pd.NA)
    return result.astype("Float64")


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_raw(source_zip: Path, raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_zip) as archive:
        archive.testzip()
        archive.extractall(raw_dir)
    missing = [name for name in SOURCE_FILES if not (raw_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Fichiers absents après extraction : {missing}")


def copy_raw(source_dir: Path, raw_dir: Path) -> None:
    """Alternative à extract_raw : copie des CSV Olist déjà extraits, sans modification."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    missing = [name for name in SOURCE_FILES if not (source_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Fichiers absents dans {source_dir} : {missing}")
    if source_dir.resolve() == raw_dir.resolve():
        return
    for name in SOURCE_FILES:
        shutil.copy2(source_dir / name, raw_dir / name)


def profile_sources(raw_dir: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    rows: list[dict[str, object]] = []
    manifest: dict[str, object] = {"files": {}}
    for name in SOURCE_FILES:
        path = raw_dir / name
        frame = pd.read_csv(path, low_memory=False)
        missing_cells = int(frame.isna().sum().sum())
        duplicate_rows = int(frame.duplicated().sum())
        rows.append(
            {
                "file": name,
                "rows": int(len(frame)),
                "columns": int(len(frame.columns)),
                "missing_cells": missing_cells,
                "exact_duplicate_rows": duplicate_rows,
                "size_bytes": int(path.stat().st_size),
                "sha256": sha256(path),
            }
        )
        manifest["files"][name] = {
            "rows": int(len(frame)),
            "columns": list(frame.columns),
            "missing_by_column": {key: int(value) for key, value in frame.isna().sum().items()},
            "exact_duplicate_rows": duplicate_rows,
            "size_bytes": int(path.stat().st_size),
            "sha256": sha256(path),
        }
    return pd.DataFrame(rows), manifest


def aggregate_items(items: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    product_fields = [
        "product_id",
        "category_name",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]
    item_detail = items.merge(products[product_fields], on="product_id", how="left", validate="many_to_one")
    item_detail["product_volume_cm3"] = (
        item_detail["product_length_cm"]
        * item_detail["product_height_cm"]
        * item_detail["product_width_cm"]
    )
    grouped = item_detail.groupby("order_id", sort=False)
    result = grouped.agg(
        item_count=("order_item_id", "count"),
        product_count=("product_id", "nunique"),
        seller_count=("seller_id", "nunique"),
        item_price_total=("price", "sum"),
        freight_total=("freight_value", "sum"),
        product_weight_mean_g=("product_weight_g", "mean"),
        product_volume_mean_cm3=("product_volume_cm3", "mean"),
        # Date limite de remise au transporteur (engagement du vendeur, connue à l'approbation) : la plus tardive des lignes.
        shipping_limit_max=("shipping_limit_date", "max"),
    ).reset_index()
    category = grouped["category_name"].agg(mode_or_unknown).rename("primary_category").reset_index()
    sellers = grouped["seller_id"].agg(lambda s: str(s.iloc[0]) if s.nunique() == 1 else pd.NA).rename("single_seller_id").reset_index()
    result = result.merge(category, on="order_id", how="left", validate="one_to_one")
    result = result.merge(sellers, on="order_id", how="left", validate="one_to_one")
    return result


def aggregate_payments(payments: pd.DataFrame) -> pd.DataFrame:
    return (
        payments.groupby("order_id", sort=False)
        .agg(
            payment_rows=("payment_sequential", "count"),
            payment_type_count=("payment_type", "nunique"),
            payment_installments_max=("payment_installments", "max"),
            payment_total=("payment_value", "sum"),
        )
        .reset_index()
    )


def build_multi_seller_links(items: pd.DataFrame, products: pd.DataFrame, analysis: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par couple (commande multi-vendeurs, vendeur).

    Le retard et l'avis restent des attributs de la COMMANDE : ils sont répétés sur chaque
    vendeur à titre de contexte, sans être attribués à l'un d'eux. La part de chaque vendeur
    dans le montant de la commande permet des analyses pondérées explicites.
    """
    multi_ids = analysis.loc[analysis["seller_count"].gt(1), "order_id"]
    detail = items[items["order_id"].isin(multi_ids)].merge(
        products[["product_id", "category_name"]], on="product_id", how="left", validate="many_to_one"
    )
    grouped = detail.groupby(["order_id", "seller_id"], sort=False)
    links = grouped.agg(
        seller_item_count=("order_item_id", "count"),
        seller_product_count=("product_id", "nunique"),
        seller_price_total=("price", "sum"),
        seller_freight_total=("freight_value", "sum"),
        seller_shipping_limit_max=("shipping_limit_date", "max"),
    ).reset_index()
    links["seller_primary_category"] = grouped["category_name"].agg(mode_or_unknown).values
    order_total = links.groupby("order_id")["seller_price_total"].transform("sum")
    links["seller_price_share"] = (links["seller_price_total"] / order_total.replace(0, pd.NA)).astype("Float64")
    context = analysis[
        [
            "order_id",
            "purchase_month",
            "order_status",
            "customer_state",
            "seller_count",
            "is_late",
            "late_days",
            "review_score",
            "is_poor_review",
            "has_written_comment",
        ]
    ].rename(
        columns={
            "seller_count": "order_seller_count",
            "is_late": "order_is_late",
            "late_days": "order_late_days",
            "review_score": "order_review_score",
            "is_poor_review": "order_is_poor_review",
            "has_written_comment": "order_has_written_comment",
        }
    )
    links = links.merge(context, on="order_id", how="left", validate="many_to_one")
    links["attribution_note"] = "order_level_outcome_not_attributed_to_seller"
    return links


def select_reviews(reviews: pd.DataFrame) -> pd.DataFrame:
    selected = reviews.sort_values(
        ["order_id", "review_answer_timestamp", "review_id"],
        na_position="first",
    ).drop_duplicates("order_id", keep="last")
    selected = selected.copy()
    selected["has_written_comment"] = selected["review_comment_message"].fillna("").str.strip().ne("")
    selected["is_poor_review"] = selected["review_score"].le(2).astype("Int64")
    return selected


def build_order_tables(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    item_agg: pd.DataFrame,
    payment_agg: pd.DataFrame,
    selected_reviews: pd.DataFrame,
    geo_zip: pd.DataFrame,
    sellers: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    customer_fields = [
        "customer_id",
        "customer_unique_id",
        "customer_zip_code_prefix",
        "customer_city",
        "customer_state",
    ]
    review_fields = [
        "order_id",
        "review_id",
        "review_score",
        "review_comment_title",
        "review_comment_message",
        "review_creation_date",
        "review_answer_timestamp",
        "has_written_comment",
        "is_poor_review",
    ]
    analysis = orders.merge(customers[customer_fields], on="customer_id", how="left", validate="many_to_one")
    analysis = analysis.merge(item_agg, on="order_id", how="left", validate="one_to_one")
    analysis = analysis.merge(payment_agg, on="order_id", how="left", validate="one_to_one")
    analysis = analysis.merge(selected_reviews[review_fields], on="order_id", how="left", validate="one_to_one")

    count_fields = ["item_count", "product_count", "seller_count", "payment_rows", "payment_type_count"]
    for column in count_fields:
        analysis[column] = analysis[column].fillna(0).astype("Int64")
    # Commande sans article : étiquette distincte de « produit sans catégorie ».
    analysis["has_items"] = analysis["item_count"].gt(0)
    analysis["primary_category"] = analysis["primary_category"].where(analysis["has_items"], NO_ITEMS_LABEL)
    analysis["primary_category"] = analysis["primary_category"].fillna(UNKNOWN_CATEGORY_LABEL)
    analysis["is_multi_seller"] = analysis["seller_count"].gt(1)
    # État du vendeur (commandes mono-vendeur uniquement) : utilisé par BO3 pour les groupes de pairs.
    if sellers is not None:
        seller_state = sellers[["seller_id", "seller_state"]].rename(columns={"seller_id": "single_seller_id"})
        analysis = analysis.merge(seller_state, on="single_seller_id", how="left", validate="many_to_one")

    # Coordonnées du client à partir du centroïde de son préfixe postal (connu à l'achat).
    customer_geo = geo_zip.loc[
        geo_zip["is_within_brazil"],
        ["geolocation_zip_code_prefix", "latitude", "longitude"],
    ].rename(
        columns={
            "geolocation_zip_code_prefix": "customer_zip_code_prefix",
            "latitude": "customer_lat",
            "longitude": "customer_lng",
        }
    )
    analysis = analysis.merge(customer_geo, on="customer_zip_code_prefix", how="left", validate="many_to_one")
    analysis["customer_has_geo"] = analysis["customer_lat"].notna()

    analysis["purchase_month"] = analysis["order_purchase_timestamp"].dt.to_period("M").astype(str)
    analysis["purchase_weekday"] = analysis["order_purchase_timestamp"].dt.dayofweek.astype("Int64")
    analysis["purchase_hour"] = analysis["order_purchase_timestamp"].dt.hour.astype("Int64")
    analysis["approval_delay_hours"] = (
        analysis["order_approved_at"] - analysis["order_purchase_timestamp"]
    ).dt.total_seconds() / 3600
    # Durée observée uniquement pour les commandes au statut « delivered » avec date réelle.
    # Les 6 commandes annulées/autres possédant malgré tout une date de livraison sont exclues.
    analysis["delivery_observed"] = (
        analysis["order_status"].eq("delivered") & analysis["order_delivered_customer_date"].notna()
    )
    analysis["delivery_duration_days"] = (
        (analysis["order_delivered_customer_date"] - analysis["order_purchase_timestamp"]).dt.total_seconds() / 86400
    ).where(analysis["delivery_observed"])

    # Incohérences de dates : signalées, jamais corrigées ni supprimées silencieusement.
    analysis["flag_carrier_before_approval"] = (
        analysis["order_delivered_carrier_date"] < analysis["order_approved_at"]
    )
    analysis["flag_delivered_before_carrier"] = (
        analysis["order_delivered_customer_date"] < analysis["order_delivered_carrier_date"]
    )
    analysis["flag_delivered_status_missing_date"] = (
        analysis["order_status"].eq("delivered") & analysis["order_delivered_customer_date"].isna()
    )
    analysis["flag_delivery_date_on_undelivered_status"] = (
        analysis["order_status"].ne("delivered") & analysis["order_delivered_customer_date"].notna()
    )
    analysis["flag_any_date_issue"] = analysis[
        [
            "flag_carrier_before_approval",
            "flag_delivered_before_carrier",
            "flag_delivered_status_missing_date",
            "flag_delivery_date_on_undelivered_status",
        ]
    ].any(axis=1)
    analysis["late_days"] = (
        analysis["order_delivered_customer_date"].dt.normalize()
        - analysis["order_estimated_delivery_date"].dt.normalize()
    ).dt.days
    analysis["late_label_eligible"] = (
        analysis["order_status"].eq("delivered")
        & analysis["order_delivered_customer_date"].notna()
        & analysis["order_estimated_delivery_date"].notna()
    )
    analysis["is_late"] = pd.Series(pd.NA, index=analysis.index, dtype="Int64")
    eligible = analysis["late_label_eligible"]
    analysis.loc[eligible, "is_late"] = analysis.loc[eligible, "late_days"].gt(0).astype("int64")
    analysis["poor_review_label_eligible"] = analysis["review_score"].notna()
    # Remise tardive au transporteur (BO3) : jour de remise réel > jour limite d'expédition fixé au vendeur.
    # C'est le signal le plus imputable au vendeur (le retard de livraison mêle vendeur et transporteur).
    analysis["handover_label_eligible"] = (
        analysis["order_delivered_carrier_date"].notna() & analysis["shipping_limit_max"].notna()
    )
    analysis["handover_delay_days"] = (
        analysis["order_delivered_carrier_date"].dt.normalize() - analysis["shipping_limit_max"].dt.normalize()
    ).dt.days.where(analysis["handover_label_eligible"])
    analysis["is_late_handover"] = pd.Series(pd.NA, index=analysis.index, dtype="Int64")
    h_eligible = analysis["handover_label_eligible"]
    analysis.loc[h_eligible, "is_late_handover"] = analysis.loc[h_eligible, "handover_delay_days"].gt(0).astype("int64")
    analysis["is_poor_review"] = analysis["is_poor_review"].astype("Int64")
    analysis["has_written_comment"] = analysis["has_written_comment"].fillna(False).astype(bool)

    model_columns = [
        "order_id",
        "order_purchase_timestamp",
        "order_approved_at",
        "purchase_month",
        "purchase_weekday",
        "purchase_hour",
        "approval_delay_hours",
        "customer_state",
        "customer_city",
        "customer_zip_code_prefix",
        "customer_lat",
        "customer_lng",
        "customer_has_geo",
        "has_items",
        "item_count",
        "product_count",
        "seller_count",
        "is_multi_seller",
        "single_seller_id",
        "primary_category",
        "item_price_total",
        "freight_total",
        "product_weight_mean_g",
        "product_volume_mean_cm3",
        "payment_rows",
        "payment_type_count",
        "payment_installments_max",
        "payment_total",
        "late_label_eligible",
        "is_late",
        "poor_review_label_eligible",
        "is_poor_review",
    ]
    return analysis, analysis[model_columns].copy()


def aggregate_kpis(frame: pd.DataFrame, dimensions: list[str]) -> pd.DataFrame:
    grouped = frame.groupby(dimensions, dropna=False, observed=True)
    result = grouped.agg(
        order_count=("order_id", "nunique"),
        delivered_order_count=("order_status", lambda s: int(s.eq("delivered").sum())),
        late_eligible_count=("late_label_eligible", "sum"),
        late_order_count=("is_late", lambda s: int(s.fillna(0).sum())),
        observed_delivery_count=("delivery_duration_days", "count"),
        delivery_duration_mean_days=("delivery_duration_days", "mean"),
        delivery_duration_median_days=("delivery_duration_days", "median"),
        reviewed_order_count=("review_score", "count"),
        poor_review_count=("is_poor_review", lambda s: int(s.fillna(0).sum())),
        average_review_score=("review_score", "mean"),
        written_comment_count=("has_written_comment", "sum"),
        item_price_total=("item_price_total", "sum"),
        freight_total=("freight_total", "sum"),
    ).reset_index()
    result["late_rate"] = safe_rate(result["late_order_count"], result["late_eligible_count"])
    result["poor_review_rate"] = safe_rate(result["poor_review_count"], result["reviewed_order_count"])
    result["written_comment_rate"] = safe_rate(result["written_comment_count"], result["reviewed_order_count"])
    return result


def complete_month_range(monthly: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les mois sans aucune commande (ex. 2016-11) pour qu'un graphique ne les saute pas."""
    months = pd.period_range(monthly["purchase_month"].min(), monthly["purchase_month"].max(), freq="M").astype(str)
    full = pd.DataFrame({"purchase_month": months}).merge(monthly, on="purchase_month", how="left")
    count_columns = [c for c in full.columns if c.endswith("_count") or c in ("item_price_total", "freight_total")]
    full[count_columns] = full[count_columns].fillna(0)
    integer_columns = [c for c in count_columns if c.endswith("_count")]
    full[integer_columns] = full[integer_columns].astype("int64")
    return full


def period_status_table(monthly: pd.DataFrame) -> pd.DataFrame:
    status = monthly[["purchase_month", "order_count"]].rename(columns={"order_count": "period_order_count"})
    status["is_complete_period"] = status["period_order_count"].ge(SPARSE_MONTH_MIN_ORDERS)
    status["period_status"] = status["period_order_count"].map(
        lambda n: "no_orders" if n == 0 else ("sparse" if n < SPARSE_MONTH_MIN_ORDERS else "complete")
    )
    return status


def add_period_status(frame: pd.DataFrame, status: pd.DataFrame) -> pd.DataFrame:
    return frame.merge(
        status[["purchase_month", "is_complete_period", "period_status"]],
        on="purchase_month",
        how="left",
        validate="many_to_one",
    )


def build_seller_kpis(analysis: pd.DataFrame) -> pd.DataFrame:
    single = analysis[analysis["seller_count"].eq(1) & analysis["single_seller_id"].notna()].copy()
    return aggregate_kpis(single, ["purchase_month", "single_seller_id"])


def write_reviews_jsonl(reviews: pd.DataFrame, analysis: pd.DataFrame, output: Path) -> tuple[int, int]:
    context = analysis[
        ["order_id", "purchase_month", "customer_state", "primary_category", "is_late", "delivery_duration_days"]
    ]
    docs = reviews.merge(context, on="order_id", how="left", validate="many_to_one")
    has_message = docs["review_comment_message"].fillna("").str.strip().ne("")
    has_title = docs["review_comment_title"].fillna("").str.strip().ne("")
    docs = docs.assign(has_message=has_message, has_title=has_title)
    # Tout texte libre est conservé : message ET/OU titre. `has_message` permet de retrouver
    # le périmètre « commentaire écrit » (40 950) utilisé dans le rapport.
    docs = docs[docs["has_message"] | docs["has_title"]].copy()
    output.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(output, "wt", encoding="utf-8") as stream:
        for row in docs.itertuples(index=False):
            record = {
                "review_id": row.review_id,
                "order_id": row.order_id,
                "review_score": int(row.review_score),
                "title": str(row.review_comment_title).strip() if row.has_title else None,
                "text": str(row.review_comment_message).strip() if row.has_message else None,
                "has_message": bool(row.has_message),
                "has_title": bool(row.has_title),
                "review_created_at": row.review_creation_date.isoformat() if pd.notna(row.review_creation_date) else None,
                "review_answered_at": row.review_answer_timestamp.isoformat() if pd.notna(row.review_answer_timestamp) else None,
                "metadata": {
                    "purchase_month": row.purchase_month,
                    "customer_state": row.customer_state,
                    "primary_category": row.primary_category,
                    "is_late": None if pd.isna(row.is_late) else int(row.is_late),
                    "delivery_duration_days": None if pd.isna(row.delivery_duration_days) else round(float(row.delivery_duration_days), 4),
                },
            }
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return int(len(docs)), int(docs["has_message"].sum())


def build_geo_zip(geolocation: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Centroïde par préfixe postal, calculé uniquement sur les points situés au Brésil.

    Les points hors emprise (erreurs de saisie de la source) sont exclus du calcul ; un préfixe
    dont tous les points sont hors emprise est conservé mais marqué is_within_brazil = False.
    """
    unique = geolocation.drop_duplicates().copy()
    b = BRAZIL_BBOX
    unique["point_within_brazil"] = unique["geolocation_lat"].between(b["lat_min"], b["lat_max"]) & unique[
        "geolocation_lng"
    ].between(b["lng_min"], b["lng_max"])
    stats = {
        "raw_points": int(len(geolocation)),
        "exact_duplicate_points_removed": int(len(geolocation) - len(unique)),
        "points_outside_brazil_excluded": int((~unique["point_within_brazil"]).sum()),
    }
    valid = unique[unique["point_within_brazil"]]
    centroid = (
        valid.groupby("geolocation_zip_code_prefix", dropna=False)
        .agg(
            latitude=("geolocation_lat", "mean"),
            longitude=("geolocation_lng", "mean"),
            city=("geolocation_city", mode_or_unknown),
            state=("geolocation_state", mode_or_unknown),
            source_observation_count=("geolocation_lat", "count"),
        )
        .reset_index()
    )
    all_prefixes = unique[["geolocation_zip_code_prefix"]].drop_duplicates()
    excluded = (
        unique[~unique["point_within_brazil"]]
        .groupby("geolocation_zip_code_prefix")
        .size()
        .rename("excluded_outside_points")
        .reset_index()
    )
    geo_zip = all_prefixes.merge(centroid, on="geolocation_zip_code_prefix", how="left")
    geo_zip = geo_zip.merge(excluded, on="geolocation_zip_code_prefix", how="left")
    geo_zip["excluded_outside_points"] = geo_zip["excluded_outside_points"].fillna(0).astype("int64")
    geo_zip["source_observation_count"] = geo_zip["source_observation_count"].fillna(0).astype("int64")
    geo_zip["is_within_brazil"] = geo_zip["latitude"].notna()
    stats["zip_prefixes"] = int(len(geo_zip))
    stats["zip_prefixes_without_valid_point"] = int((~geo_zip["is_within_brazil"]).sum())
    return geo_zip, stats


def build_metric_catalog() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["order_count", "Nombre de commandes distinctes", "COUNT DISTINCT order_id", "Toutes les commandes", "OM5"],
            ["late_rate", "Taux de livraisons après le jour promis", "late_order_count / late_eligible_count", "Commandes livrées avec dates réelle et estimée", "OM1, OM5"],
            ["delivery_duration_mean_days", "Durée moyenne entre achat et livraison", "AVG(delivered_at - purchased_at)", "Commandes au statut delivered avec date réelle", "OM4, OM5"],
            ["poor_review_rate", "Part des avis notés 1 ou 2", "poor_review_count / reviewed_order_count", "Commandes avec avis sélectionné", "OM1, OM2, OM5"],
            ["average_review_score", "Note moyenne", "AVG(review_score)", "Commandes avec avis sélectionné", "OM2, OM3, OM5"],
            ["written_comment_rate", "Part des avis contenant un commentaire", "written_comment_count / reviewed_order_count", "Commandes avec avis sélectionné", "OM2, OM5"],
            ["item_price_total", "Somme des prix articles, sans frais", "SUM(item price) après agrégation commande", "Commandes avec articles", "OM3, OM5"],
            ["freight_total", "Somme des frais de transport", "SUM(freight_value) après agrégation commande", "Commandes avec articles", "OM3, OM5"],
            ["date_issue_count", "Commandes présentant une incohérence de dates", "SUM(flag_any_date_issue)", "Toutes les commandes", "OM5"],
            ["is_complete_period", "Mois exploitable comme tendance", f"order_count du mois >= {SPARSE_MONTH_MIN_ORDERS}", "Mois d'achat", "OM5 (filtre obligatoire des graphiques)"],
        ],
        columns=["metric_id", "description", "calculation", "population", "objectives"],
    )


# Empreintes SHA-256 des 9 fichiers Olist originaux (Kaggle, version vérifiée en phase 2).
EXPECTED_SOURCE_SHA256 = {
    "olist_customers_dataset.csv": "983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2",
    "olist_geolocation_dataset.csv": "b514f6fc991b9566aeba02aa5d67e2c3630f034b60a0e05aa0d082a3b66d88d6",
    "olist_order_items_dataset.csv": "0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279",
    "olist_order_payments_dataset.csv": "4f713964f2815dbbaa40b9488268c55aac3627bfce5aa96cf58d1f3616de3cc0",
    "olist_order_reviews_dataset.csv": "012b61c7593e34f51fa614efdf802b9c7056ce6aae5307ddb93236e7cfc797d7",
    "olist_orders_dataset.csv": "8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf",
    "olist_products_dataset.csv": "3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc",
    "olist_sellers_dataset.csv": "1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e",
    "product_category_name_translation.csv": "a81f0d1f27b27e7293f761bc79e3ce8f348ee39c4b3ed3e49bde38f478586278",
}

# Colonnes postérieures à l'approbation, interdites dans la base de modélisation.
FORBIDDEN_MODEL_COLUMNS = [
    "order_status",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
    "delivery_duration_days",
    "delivery_observed",
    "late_days",
    "review_id",
    "review_score",
    "review_comment_title",
    "review_comment_message",
    "review_creation_date",
    "review_answer_timestamp",
    "has_written_comment",
    "flag_carrier_before_approval",
    "flag_delivered_before_carrier",
    "flag_delivered_status_missing_date",
    "flag_delivery_date_on_undelivered_status",
    "flag_any_date_issue",
]


def build_quality_report(ctx: dict[str, object]) -> tuple[pd.DataFrame, str]:
    inv: pd.DataFrame = ctx["source_inventory"]
    a: pd.DataFrame = ctx["analysis"]
    m: pd.DataFrame = ctx["model_base"]
    raw: dict[str, pd.DataFrame] = ctx["raw"]
    o, it, pay, rv = raw["orders"], raw["items"], raw["payments"], raw["reviews"]
    monthly: pd.DataFrame = ctx["monthly"]
    links: pd.DataFrame = ctx["multi_seller_links"]
    seller: pd.DataFrame = ctx["seller_monthly"]
    geo: pd.DataFrame = ctx["geo_zip"]

    sha_ok = all(
        inv.set_index("file").loc[name, "sha256"] == expected for name, expected in EXPECTED_SOURCE_SHA256.items()
    )
    orphan = {
        "items_to_orders": int((~it["order_id"].isin(o["order_id"])).sum()),
        "items_to_products": int((~it["product_id"].isin(raw["products"]["product_id"])).sum()),
        "items_to_sellers": int((~it["seller_id"].isin(raw["sellers"]["seller_id"])).sum()),
        "payments_to_orders": int((~pay["order_id"].isin(o["order_id"])).sum()),
        "reviews_to_orders": int((~rv["order_id"].isin(o["order_id"])).sum()),
        "orders_to_customers": int((~o["customer_id"].isin(raw["customers"]["customer_id"])).sum()),
    }
    sparse_months = monthly.loc[~monthly["is_complete_period"], "purchase_month"].tolist()
    months = pd.period_range(monthly["purchase_month"].min(), monthly["purchase_month"].max(), freq="M").astype(str)
    multi_ids = set(a.loc[a["is_multi_seller"], "order_id"])

    def row(check, category, observed, expected, passed):
        return [check, category, observed, expected, bool(passed)]

    checks = [
        row("source_file_count", "Sources", len(inv), 9, len(inv) == 9),
        row("source_sha256_unchanged", "Sources", "identiques" if sha_ok else "différents", "identiques", sha_ok),
        row("orders_rows", "Grain commande", len(a), 99441, len(a) == 99441),
        row("duplicate_order_id", "Grain commande", int(a["order_id"].duplicated().sum()), 0, not a["order_id"].duplicated().any()),
        row("item_price_total_matches_raw", "Agrégation avant jointure", round(float(a["item_price_total"].sum()), 2), round(float(it["price"].sum()), 2), abs(a["item_price_total"].sum() - it["price"].sum()) < 0.01),
        row("freight_total_matches_raw", "Agrégation avant jointure", round(float(a["freight_total"].sum()), 2), round(float(it["freight_value"].sum()), 2), abs(a["freight_total"].sum() - it["freight_value"].sum()) < 0.01),
        row("payment_total_matches_raw", "Agrégation avant jointure", round(float(a["payment_total"].sum()), 2), round(float(pay["payment_value"].sum()), 2), abs(a["payment_total"].sum() - pay["payment_value"].sum()) < 0.01),
    ]
    for name, value in orphan.items():
        checks.append(row(f"orphan_{name}", "Intégrité référentielle", value, 0, value == 0))
    checks += [
        row("orders_without_items_labelled_no_items", "Couverture", int(a["primary_category"].eq(NO_ITEMS_LABEL).sum()), 775, int(a["primary_category"].eq(NO_ITEMS_LABEL).sum()) == int((~a["has_items"]).sum()) == 775),
        row("orders_without_review_kept", "Couverture", int(a["review_score"].isna().sum()), 768, int(a["review_score"].isna().sum()) == 768),
        row("selected_review_one_per_order", "Avis", int(a["review_id"].notna().sum()), 98673, int(a["review_id"].notna().sum()) == 98673),
        row("written_comment_documents", "Avis", ctx["message_docs"], 40950, ctx["message_docs"] == 40950),
        row("all_free_text_documents", "Avis", ctx["text_docs"], 42687, ctx["text_docs"] == 42687),
        row("late_eligible_count", "Retard", int(a["late_label_eligible"].sum()), 96470, int(a["late_label_eligible"].sum()) == 96470),
        row("late_order_count", "Retard", int(a["is_late"].fillna(0).sum()), 6534, int(a["is_late"].fillna(0).sum()) == 6534),
        row("is_late_missing_when_not_eligible", "Retard", int(a.loc[~a["late_label_eligible"], "is_late"].notna().sum()), 0, a.loc[~a["late_label_eligible"], "is_late"].isna().all()),
        row("delivery_duration_observed", "Durée de livraison", int(a["delivery_duration_days"].notna().sum()), 96470, int(a["delivery_duration_days"].notna().sum()) == 96470),
        row("multi_seller_orders", "Multi-vendeurs", len(multi_ids), 1278, len(multi_ids) == 1278),
        row("multi_seller_links_cover_all_orders", "Multi-vendeurs", int(links["order_id"].nunique()), 1278, set(links["order_id"]) == multi_ids),
        row("multi_seller_price_share_sums_to_1", "Multi-vendeurs", "oui" if (links.groupby("order_id")["seller_price_share"].sum() - 1).abs().max() < 1e-9 else "non", "oui", (links.groupby("order_id")["seller_price_share"].sum() - 1).abs().max() < 1e-9),
        row("seller_kpis_exclude_multi_seller", "Multi-vendeurs", int(seller["order_count"].sum()), int(a["seller_count"].eq(1).sum()), int(seller["order_count"].sum()) == int(a["seller_count"].eq(1).sum())),
        row("model_base_rows", "Fuite d'information", len(m), 99441, len(m) == 99441),
        row("model_base_forbidden_columns", "Fuite d'information", ", ".join(c for c in FORBIDDEN_MODEL_COLUMNS if c in m.columns) or "aucune", "aucune", not any(c in m.columns for c in FORBIDDEN_MODEL_COLUMNS)),
        row("monthly_kpis_no_missing_month", "Périodes", len(monthly), len(months), list(monthly["purchase_month"]) == list(months)),
        row("sparse_months_flagged", "Périodes", ", ".join(sparse_months), "2016-09, 2016-11, 2016-12, 2018-09, 2018-10", sparse_months == ["2016-09", "2016-11", "2016-12", "2018-09", "2018-10"]),
        row("monthly_order_sum", "Périodes", int(monthly["order_count"].sum()), 99441, int(monthly["order_count"].sum()) == 99441),
        row("flag_carrier_before_approval", "Dates (signalées)", int(a["flag_carrier_before_approval"].sum()), 1359, int(a["flag_carrier_before_approval"].sum()) == 1359),
        row("flag_delivered_before_carrier", "Dates (signalées)", int(a["flag_delivered_before_carrier"].sum()), 23, int(a["flag_delivered_before_carrier"].sum()) == 23),
        row("flag_delivered_status_missing_date", "Dates (signalées)", int(a["flag_delivered_status_missing_date"].sum()), 8, int(a["flag_delivered_status_missing_date"].sum()) == 8),
        row("flag_delivery_date_on_undelivered_status", "Dates (signalées)", int(a["flag_delivery_date_on_undelivered_status"].sum()), 6, int(a["flag_delivery_date_on_undelivered_status"].sum()) == 6),
        row("geo_centroids_outside_brazil", "Géolocalisation", int((geo["is_within_brazil"] & ~(geo["latitude"].between(BRAZIL_BBOX["lat_min"], BRAZIL_BBOX["lat_max"]) & geo["longitude"].between(BRAZIL_BBOX["lng_min"], BRAZIL_BBOX["lng_max"]))).sum()), 0, (geo.loc[geo["is_within_brazil"], "latitude"].between(BRAZIL_BBOX["lat_min"], BRAZIL_BBOX["lat_max"]).all())),
        row("customers_with_geo", "Géolocalisation", int(a["customer_has_geo"].sum()), "information", True),
        row("late_handover_label_only_when_eligible", "Remise au transporteur",
            f"{int(a['is_late_handover'].notna().sum())} étiquetées / {int(a['handover_label_eligible'].sum())} éligibles", "égalité",
            int(a["is_late_handover"].notna().sum()) == int(a["handover_label_eligible"].sum())),
        row("shipping_limit_matches_raw", "Remise au transporteur",
            int(a["shipping_limit_max"].notna().sum()), int(it["order_id"].nunique()),
            int(a["shipping_limit_max"].notna().sum()) == int(it["order_id"].nunique())),
    ]
    table = pd.DataFrame(checks, columns=["check", "category", "observed", "expected", "passed"])
    status = "RÉUSSI" if bool(table["passed"].all()) else "ÉCHEC"
    gs = ctx["geo_stats"]
    text = f"""# Rapport de qualité des données

Statut global : **{status}** — {int(table['passed'].sum())}/{len(table)} contrôles réussis.

| Catégorie | Contrôle | Observé | Attendu | Résultat |
|---|---|---:|---:|---|
"""
    for r in table.itertuples(index=False):
        text += f"| {r.category} | {r.check} | {r.observed} | {r.expected} | {'OK' if r.passed else 'À corriger'} |\n"
    text += f"""
## Règles appliquées

- Les articles et paiements sont agrégés au niveau commande avant les jointures ; les totaux sont égaux aux fichiers bruts.
- Un seul avis est retenu pour les cibles commande : le dernier `review_answer_timestamp`, puis `review_id` pour départager. Tout le texte libre (messages et titres) reste disponible dans `reviews_text.jsonl.gz`.
- Les 775 commandes sans article portent la catégorie `{NO_ITEMS_LABEL}` ; `{UNKNOWN_CATEGORY_LABEL}` est réservé aux produits sans catégorie.
- Le retard compare les jours calendaires de livraison réelle et promise. Une commande sans date réelle n'est jamais classée automatiquement à l'heure.
- La durée de livraison n'est calculée que pour les commandes au statut `delivered` avec date réelle (96 470).
- Les 1 278 commandes multi-vendeurs sont exclues des KPI vendeurs et analysées à part dans `multi_seller_order_links.csv.gz`, sans attribution du retard ou de l'avis à un vendeur.
- Les variables futures restent dans `orders_analysis.csv.gz`, mais sont exclues de `orders_model_base.csv.gz`.
- Les mois de moins de {SPARSE_MONTH_MIN_ORDERS} commandes, et le mois sans commande 2016-11, sont marqués `is_complete_period = False` dans toutes les tables KPI. Ils doivent être exclus des graphiques de tendance.
- Les incohérences de dates sont signalées par des colonnes `flag_*`, jamais corrigées ni supprimées.
- Géolocalisation : {gs['exact_duplicate_points_removed']} points dupliqués retirés et {gs['points_outside_brazil_excluded']} points hors du Brésil exclus du calcul des centroïdes ; {gs['zip_prefixes_without_valid_point']} préfixes n'ont plus de point valide.
"""
    return table, text


def build_data_dictionary(frames: dict[str, pd.DataFrame]) -> str:
    text = "# Dictionnaire des tables préparées\n\n"
    grains = {
        "orders_analysis": "une ligne par commande, avec résultats rétrospectifs et indicateurs d'incohérence de dates",
        "orders_model_base": "une ligne par commande, variables disponibles à l'approbation et cibles séparées",
        "multi_seller_order_links": "une ligne par couple (commande multi-vendeurs, vendeur) ; retard et avis restent des attributs de la commande",
        "seller_monthly_kpis": "une ligne par vendeur et mois, commandes mono-vendeur",
        "monthly_business_kpis": "une ligne par mois d'achat, y compris les mois sans commande",
        "state_monthly_kpis": "une ligne par mois et État client",
        "category_monthly_kpis": "une ligne par mois et catégorie principale",
        "geo_zip_centroid": "une ligne par préfixe postal ; centroïde calculé sur les points situés au Brésil",
    }
    for name, frame in frames.items():
        text += f"## {name}\n\nGrain : " + grains.get(name, "table préparée") + ".\n\n"
        text += "| Colonne | Type | Valeurs manquantes |\n|---|---|---:|\n"
        for column in frame.columns:
            text += f"| `{column}` | {frame[column].dtype} | {int(frame[column].isna().sum())} |\n"
        text += "\n"
    return text


def prepare(source_zip: Path | None, project_dir: Path, raw_source_dir: Path | None = None) -> None:
    raw = project_dir / "data" / "raw"
    bronze = project_dir / "data" / "bronze"
    silver = project_dir / "data" / "silver"
    gold = project_dir / "data" / "gold"
    quality = project_dir / "quality"
    docs = project_dir / "docs"
    for directory in [bronze, silver, gold, quality, docs]:
        directory.mkdir(parents=True, exist_ok=True)

    if source_zip is not None:
        extract_raw(source_zip, raw)
    else:
        copy_raw(raw_source_dir, raw)
    source_inventory, manifest = profile_sources(raw)
    manifest.update(
        {
            "source_archive": str(source_zip) if source_zip else None,
            "source_archive_sha256": sha256(source_zip) if source_zip else None,
            "raw_files_match_expected_sha256": all(
                manifest["files"][n]["sha256"] == h for n, h in EXPECTED_SOURCE_SHA256.items()
            ),
            "source_url": "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce",
            "license_as_displayed_by_source": "CC BY-NC-SA 4.0",
        }
    )
    source_inventory.to_csv(bronze / "source_inventory.csv", index=False)
    write_json(bronze / "source_manifest.json", manifest)

    customers = read_csv(raw / "olist_customers_dataset.csv", dtype={"customer_zip_code_prefix": "string"})
    orders = read_csv(raw / "olist_orders_dataset.csv")
    items = read_csv(raw / "olist_order_items_dataset.csv")
    payments = read_csv(raw / "olist_order_payments_dataset.csv")
    reviews = read_csv(raw / "olist_order_reviews_dataset.csv")
    products = read_csv(raw / "olist_products_dataset.csv")
    sellers = read_csv(raw / "olist_sellers_dataset.csv")
    translation = read_csv(raw / "product_category_name_translation.csv")
    geolocation = read_csv(raw / "olist_geolocation_dataset.csv", dtype={"geolocation_zip_code_prefix": "string"})

    products = products.merge(translation, on="product_category_name", how="left", validate="many_to_one")
    products["category_name"] = (
        products["product_category_name_english"].fillna(products["product_category_name"]).fillna(UNKNOWN_CATEGORY_LABEL)
    )
    geo_zip, geo_stats = build_geo_zip(geolocation)
    item_agg = aggregate_items(items, products)
    payment_agg = aggregate_payments(payments)
    selected_reviews = select_reviews(reviews)
    analysis, model_base = build_order_tables(orders, customers, item_agg, payment_agg, selected_reviews, geo_zip, sellers)
    multi_links = build_multi_seller_links(items, products, analysis)

    analysis_for_kpi = analysis.assign(date_issue=analysis["flag_any_date_issue"].astype(int))
    monthly = complete_month_range(aggregate_kpis(analysis_for_kpi, ["purchase_month"]))
    period_status = period_status_table(monthly)
    monthly = add_period_status(monthly, period_status)
    state_monthly = add_period_status(aggregate_kpis(analysis_for_kpi, ["purchase_month", "customer_state"]), period_status)
    category_monthly = add_period_status(aggregate_kpis(analysis_for_kpi, ["purchase_month", "primary_category"]), period_status)
    seller_monthly = add_period_status(build_seller_kpis(analysis_for_kpi), period_status)
    date_issues = analysis_for_kpi.groupby("purchase_month")["date_issue"].sum().rename("date_issue_count").reset_index()
    monthly = monthly.merge(date_issues, on="purchase_month", how="left")
    monthly["date_issue_count"] = monthly["date_issue_count"].fillna(0).astype("int64")
    metric_catalog = build_metric_catalog()

    analysis.to_csv(silver / "orders_analysis.csv.gz", index=False, compression="gzip")
    model_base.to_csv(silver / "orders_model_base.csv.gz", index=False, compression="gzip")
    selected_reviews.to_csv(silver / "reviews_selected.csv.gz", index=False, compression="gzip")
    multi_links.to_csv(silver / "multi_seller_order_links.csv.gz", index=False, compression="gzip")
    seller_monthly.to_csv(silver / "seller_monthly_kpis.csv.gz", index=False, compression="gzip")
    geo_zip.to_csv(silver / "geo_zip_centroid.csv.gz", index=False, compression="gzip")
    text_docs, message_docs = write_reviews_jsonl(reviews, analysis, silver / "reviews_text.jsonl.gz")

    monthly.to_csv(gold / "monthly_business_kpis.csv", index=False)
    state_monthly.to_csv(gold / "state_monthly_kpis.csv.gz", index=False, compression="gzip")
    category_monthly.to_csv(gold / "category_monthly_kpis.csv.gz", index=False, compression="gzip")
    metric_catalog.to_csv(gold / "metric_catalog.csv", index=False)

    quality_table, quality_text = build_quality_report(
        {
            "source_inventory": source_inventory,
            "analysis": analysis,
            "model_base": model_base,
            "raw": {
                "orders": orders,
                "items": items,
                "payments": payments,
                "reviews": reviews,
                "products": products,
                "sellers": sellers,
                "customers": customers,
            },
            "monthly": monthly,
            "multi_seller_links": multi_links,
            "seller_monthly": seller_monthly,
            "geo_zip": geo_zip,
            "geo_stats": geo_stats,
            "text_docs": text_docs,
            "message_docs": message_docs,
        }
    )
    quality_table.to_csv(quality / "quality_checks.csv", index=False)
    (quality / "quality_report.md").write_text(quality_text, encoding="utf-8")

    frames = {
        "orders_analysis": analysis,
        "orders_model_base": model_base,
        "multi_seller_order_links": multi_links,
        "seller_monthly_kpis": seller_monthly,
        "monthly_business_kpis": monthly,
        "state_monthly_kpis": state_monthly,
        "category_monthly_kpis": category_monthly,
        "geo_zip_centroid": geo_zip,
    }
    (docs / "data_dictionary.md").write_text(build_data_dictionary(frames), encoding="utf-8")

    run_summary = {
        "source_archive_sha256": manifest["source_archive_sha256"],
        "raw_files_match_expected_sha256": manifest["raw_files_match_expected_sha256"],
        "orders_analysis_rows": int(len(analysis)),
        "orders_model_base_rows": int(len(model_base)),
        "review_text_documents": text_docs,
        "review_documents_with_message": message_docs,
        "multi_seller_link_rows": int(len(multi_links)),
        "seller_monthly_rows": int(len(seller_monthly)),
        "monthly_kpi_rows": int(len(monthly)),
        "complete_months": int(monthly["is_complete_period"].sum()),
        "state_monthly_rows": int(len(state_monthly)),
        "category_monthly_rows": int(len(category_monthly)),
        "orders_with_date_issue": int(analysis["flag_any_date_issue"].sum()),
        "geolocation": geo_stats,
        "quality_checks": f"{int(quality_table['passed'].sum())}/{len(quality_table)}",
        "quality_checks_passed": bool(quality_table["passed"].all()),
    }
    write_json(project_dir / "run_summary.json", run_summary)
    print(json.dumps(run_summary, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Préparation des données Olist pour REHEARSE phase 2")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-zip", type=Path, help="Archive Olist d'origine (Kaggle)")
    source.add_argument("--raw-dir", type=Path, help="Dossier contenant les 9 CSV Olist déjà extraits")
    parser.add_argument("--project-dir", required=True, type=Path)
    args = parser.parse_args()
    prepare(
        args.source_zip.resolve() if args.source_zip else None,
        args.project_dir.resolve(),
        args.raw_dir.resolve() if args.raw_dir else None,
    )


if __name__ == "__main__":
    main()
