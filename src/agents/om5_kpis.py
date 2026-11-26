"""OM5 KPI engine with retrospective and point-in-time (``as_of``) semantics.

Gold tables are reused for retrospective reporting.  Point-in-time reporting is
recomputed from the order-grain Silver table because Gold intentionally contains
outcomes observed after the end of a purchase month.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from .core import DataStore, to_native


_SELLER_HISTORY_CACHE: dict[str, pd.DataFrame] = {}


RATE_SPECS = {
    "late_rate": ("late_order_count", "late_eligible_count", "ratio"),
    "poor_review_rate": ("poor_review_count", "reviewed_order_count", "ratio"),
    "written_comment_rate": ("written_comment_count", "reviewed_order_count", "ratio"),
    "late_handover_rate": ("late_handover_count", "handover_eligible_count", "ratio"),
}

METRIC_META: dict[str, tuple[str, str, str]] = {
    "order_count": ("Nombre de commandes", "commandes", "higher"),
    "delivered_order_count": ("Commandes livrées connues", "commandes", "higher"),
    "item_price_total": ("Valeur totale des articles", "BRL", "higher"),
    "average_item_value_per_order": ("Valeur moyenne des articles par commande", "BRL/commande", "higher"),
    "late_rate": ("Taux de retard", "ratio", "lower"),
    "delivery_duration_mean_days": ("Durée moyenne de livraison", "jours", "lower"),
    "delivery_duration_median_days": ("Durée médiane de livraison", "jours", "lower"),
    "freight_total": ("Frais de livraison", "BRL", "lower"),
    "late_handover_rate": ("Taux de remise tardive au transporteur", "ratio", "lower"),
    "average_review_score": ("Note moyenne", "étoiles/5", "higher"),
    "poor_review_rate": ("Taux d'avis négatifs", "ratio", "lower"),
    "reviewed_order_count": ("Nombre d'avis connus", "avis", "higher"),
    "written_comment_rate": ("Taux de commentaires écrits", "ratio", "higher"),
}

SELLER_META: dict[str, tuple[str, str, str]] = {
    "active_seller_count": ("Vendeurs actifs", "vendeurs", "higher"),
    "evaluable_seller_count": ("Vendeurs évaluables", "vendeurs", "higher"),
    "alerted_seller_count": ("Vendeurs en alerte", "vendeurs", "lower"),
    "alerted_seller_change": ("Évolution des vendeurs en alerte", "vendeurs", "lower"),
}


@dataclass(frozen=True)
class KPIValue:
    metric_id: str
    label: str
    value: float | int | None
    unit: str
    numerator: float | int | None
    denominator: float | int | None
    period: str
    dimensions: dict[str, str]
    source: str
    available_at: str
    evidence_id: str
    quality_status: str
    mode: str
    direction: str

    def to_dict(self) -> dict[str, Any]:
        return to_native(asdict(self))


def decision_date(month: str) -> pd.Timestamp:
    """Exclusive decision cut-off: first instant of the following month."""
    try:
        return pd.Period(month, freq="M").end_time.normalize() + pd.Timedelta(days=1)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("month doit respecter le format YYYY-MM") from exc


def _safe_div(num: float, den: float) -> float | None:
    return None if not den else float(num / den)


def _known_before(s: pd.Series, cutoff: pd.Timestamp) -> pd.Series:
    return s.notna() & s.lt(cutoff)


def _as_of_row(orders: pd.DataFrame, month: str) -> dict[str, Any]:
    cutoff = decision_date(month)
    g = orders.loc[orders["purchase_month"].eq(month)].copy()
    delivered_at = pd.to_datetime(g["order_delivered_customer_date"], errors="coerce")
    carrier_at = pd.to_datetime(g["order_delivered_carrier_date"], errors="coerce")
    review_at = pd.to_datetime(g["review_answer_timestamp"], errors="coerce")
    delivered_known = _known_before(delivered_at, cutoff)
    review_known = _known_before(review_at, cutoff)
    carrier_known = _known_before(carrier_at, cutoff)
    late_eligible = delivered_known & g["order_estimated_delivery_date"].notna()
    review_eligible = review_known & g["review_score"].notna()
    handover_eligible = carrier_known & g["shipping_limit_max"].notna()
    duration = g["delivery_duration_days"].where(delivered_known)
    prices = pd.to_numeric(g["item_price_total"], errors="coerce")
    freight = pd.to_numeric(g["freight_total"], errors="coerce")
    late_n = int(g.loc[late_eligible, "is_late"].fillna(0).sum())
    poor_n = int(g.loc[review_eligible, "is_poor_review"].fillna(0).sum())
    written_n = int(g.loc[review_eligible, "has_written_comment"].fillna(False).sum())
    handover_n = int(g.loc[handover_eligible, "is_late_handover"].fillna(0).sum())
    return {
        "purchase_month": month,
        "order_count": int(g["order_id"].nunique()),
        "delivered_order_count": int(delivered_known.sum()),
        "late_eligible_count": int(late_eligible.sum()),
        "late_order_count": late_n,
        "observed_delivery_count": int(delivered_known.sum()),
        "delivery_duration_mean_days": float(duration.mean()) if duration.notna().any() else None,
        "delivery_duration_median_days": float(duration.median()) if duration.notna().any() else None,
        "reviewed_order_count": int(review_eligible.sum()),
        "poor_review_count": poor_n,
        "average_review_score": float(g.loc[review_eligible, "review_score"].mean()) if review_eligible.any() else None,
        "written_comment_count": written_n,
        "item_price_total": float(prices.sum()),
        "freight_total": float(freight.sum()),
        "late_rate": _safe_div(late_n, int(late_eligible.sum())),
        "poor_review_rate": _safe_div(poor_n, int(review_eligible.sum())),
        "written_comment_rate": _safe_div(written_n, int(review_eligible.sum())),
        "handover_eligible_count": int(handover_eligible.sum()),
        "late_handover_count": handover_n,
        "late_handover_rate": _safe_div(handover_n, int(handover_eligible.sum())),
        "average_item_value_per_order": _safe_div(float(prices.sum()), int(g["order_id"].nunique())),
        "is_complete_period": bool(g.shape[0] >= 100),
        "period_status": "complete" if g.shape[0] >= 100 else ("no_orders" if g.empty else "sparse"),
        "available_at": cutoff.isoformat(),
    }


def _retrospective_row(store: DataStore, month: str) -> dict[str, Any]:
    rows = store.monthly.loc[store.monthly["purchase_month"].eq(month)]
    if rows.empty:
        raise ValueError(f"Période indisponible : {month}")
    row = rows.iloc[0].to_dict()
    orders = store.orders.loc[store.orders["purchase_month"].eq(month)]
    row["handover_eligible_count"] = int(orders["handover_label_eligible"].fillna(False).sum())
    row["late_handover_count"] = int(orders["is_late_handover"].fillna(0).sum())
    row["late_handover_rate"] = _safe_div(row["late_handover_count"], row["handover_eligible_count"])
    row["average_item_value_per_order"] = _safe_div(float(row["item_price_total"]), int(row["order_count"]))
    observed = ["order_delivered_customer_date", "review_answer_timestamp", "order_delivered_carrier_date"]
    dates = pd.concat([pd.to_datetime(orders[c], errors="coerce") for c in observed])
    row["available_at"] = dates.max().isoformat() if dates.notna().any() else decision_date(month).isoformat()
    return row


def available_months(store: DataStore, complete_only: bool = True) -> list[str]:
    m = store.monthly
    if complete_only:
        m = m.loc[m["is_complete_period"].astype(bool)]
    return m["purchase_month"].astype(str).tolist()


def seller_monitoring(store: DataStore, month: str) -> dict[str, Any]:
    orders = store.orders.loc[store.orders["purchase_month"].eq(month)]
    active = int(orders["single_seller_id"].dropna().nunique())
    path = store.dir / "data/model/bo3_monthly_history.csv.gz"
    empty = {"active_seller_count": active, "evaluable_seller_count": None, "alerted_seller_count": None,
             "alerted_seller_change": None, "by_severity": {}, "artifact_available": False}
    if not path.exists():
        return empty
    key = str(path.resolve())
    if key not in _SELLER_HISTORY_CACHE:
        _SELLER_HISTORY_CACHE[key] = pd.read_csv(path)
    history = _SELLER_HISTORY_CACHE[key]

    def summary(period: str) -> tuple[int, set[str], dict[str, int]]:
        h = history.loc[history["month"].astype(str).eq(period)].copy()
        if h.empty:
            return 0, set(), {}
        evaluable = int(h.loc[h["eligible"].fillna(False) | h["eligible_trend"].fillna(False), "seller_id"].nunique())
        flagged = h.loc[h["alert_level"].fillna(False) | h["alert_trend"].fillna(False)]
        sellers = set(flagged["seller_id"].astype(str))
        severity_rank = {"faible": 1, "moyenne": 2, "élevée": 3}
        ranked = flagged.dropna(subset=["severity"]).assign(_rank=lambda x: x["severity"].map(severity_rank).fillna(0))
        top = ranked.sort_values("_rank").groupby("seller_id").tail(1)
        severity = top["severity"].value_counts().astype(int).to_dict()
        if len(sellers) > len(top):
            severity["non_classée"] = len(sellers) - len(top)
        return evaluable, sellers, severity

    evaluable, sellers, severity = summary(month)
    previous = str(pd.Period(month, "M") - 1)
    _, previous_sellers, _ = summary(previous)
    return {"active_seller_count": active, "evaluable_seller_count": evaluable, "alerted_seller_count": len(sellers),
            "alerted_seller_change": len(sellers) - len(previous_sellers), "by_severity": severity,
            "artifact_available": True, "previous_month": previous}


def monthly_kpis(store: DataStore, month: str, mode: str = "as_of") -> list[dict[str, Any]]:
    if mode not in {"as_of", "retrospective"}:
        raise ValueError("mode doit être 'as_of' ou 'retrospective'")
    if month not in set(store.monthly["purchase_month"].astype(str)):
        raise ValueError(f"Période indisponible : {month}")
    row = _as_of_row(store.orders, month) if mode == "as_of" else _retrospective_row(store, month)
    source = "data/silver/orders_analysis.csv.gz" if mode == "as_of" else "data/gold/monthly_business_kpis.csv"
    quality = "complete" if bool(row["is_complete_period"]) else str(row["period_status"])
    out = []
    for metric, (label, unit, direction) in METRIC_META.items():
        num = den = None
        if metric in RATE_SPECS:
            num_key, den_key, _ = RATE_SPECS[metric]
            num, den = row.get(num_key), row.get(den_key)
        elif metric == "average_item_value_per_order":
            num, den = row.get("item_price_total"), row.get("order_count")
        elif metric == "average_review_score":
            den = row.get("reviewed_order_count")
        elif metric.startswith("delivery_duration_"):
            den = row.get("observed_delivery_count")
        out.append(KPIValue(
            metric, label, row.get(metric), unit, num, den, month, {}, source,
            row["available_at"], f"om5:kpi:{mode}:{month}:{metric}", quality, mode, direction,
        ).to_dict())
    sellers = seller_monitoring(store, month)
    for metric, (label, unit, direction) in SELLER_META.items():
        status = quality if metric == "active_seller_count" or sellers["artifact_available"] else "artifact_unavailable"
        source_seller = "data/silver/orders_analysis.csv.gz" if metric == "active_seller_count" else "data/model/bo3_monthly_history.csv.gz"
        seller_mode = mode if metric == "active_seller_count" else "as_of"
        out.append(KPIValue(metric, label, sellers[metric], unit, sellers[metric], None, month, {}, source_seller,
                            row["available_at"], f"om5:kpi:{seller_mode}:{month}:{metric}", status, seller_mode, direction).to_dict())
    return out


def trend_frame(store: DataStore, mode: str = "as_of", complete_only: bool = True) -> pd.DataFrame:
    months = available_months(store, complete_only=complete_only)
    if mode == "retrospective":
        rows = [_retrospective_row(store, month) for month in months]
    elif mode == "as_of":
        rows = [_as_of_row(store.orders, month) for month in months]
    else:
        raise ValueError("mode doit être 'as_of' ou 'retrospective'")
    return pd.DataFrame(rows)

