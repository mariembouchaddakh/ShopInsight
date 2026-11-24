"""Transparent time comparisons and anomaly detectors for OM5."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import norm

from .bo3_sellers import bh, wilson
from .om5_kpis import METRIC_META, RATE_SPECS


def compare_values(current: float | None, previous: float | None, is_rate: bool = False) -> dict[str, float | None]:
    if current is None or previous is None or not np.isfinite(current) or not np.isfinite(previous):
        return {"absolute_change": None, "relative_change_pct": None, "percentage_point_change": None}
    absolute = float(current - previous)
    relative = None if previous == 0 else float(100 * absolute / abs(previous))
    return {
        "absolute_change": absolute,
        "relative_change_pct": relative,
        "percentage_point_change": float(100 * absolute) if is_rate else None,
    }


def compare_periods(frame: pd.DataFrame, month: str) -> list[dict[str, Any]]:
    frame = frame.sort_values("purchase_month").reset_index(drop=True)
    match = frame.index[frame["purchase_month"].eq(month)].tolist()
    if not match:
        raise ValueError(f"Période indisponible : {month}")
    i = match[0]
    cur = frame.iloc[i]
    prev = frame.iloc[i - 1] if i else None
    year = frame.loc[frame["purchase_month"].eq(str(pd.Period(month, "M") - 12))]
    hist = frame.iloc[max(0, i - 6):i]
    out = []
    for metric, (label, unit, direction) in METRIC_META.items():
        value = cur.get(metric)
        previous = prev.get(metric) if prev is not None else None
        row = {
            "metric_id": metric, "label": label, "unit": unit, "direction": direction,
            "period": month, "value": _finite(value), "previous_period": None if prev is None else prev["purchase_month"],
            "previous_value": _finite(previous), **compare_values(_finite(value), _finite(previous), metric in RATE_SPECS),
            "historical_median": _finite(hist[metric].median()) if metric in hist else None,
            "year_over_year": None,
        }
        if not year.empty:
            row["year_over_year"] = compare_values(_finite(value), _finite(year.iloc[0].get(metric)), metric in RATE_SPECS)
        out.append(row)
    return out


def _finite(x: Any) -> float | None:
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def robust_z(history: pd.Series, current: float) -> float | None:
    h = pd.to_numeric(history, errors="coerce").dropna().to_numpy(float)
    if len(h) < 6:
        return None
    med = float(np.median(h))
    mad = float(np.median(np.abs(h - med)))
    if mad == 0:
        return 0.0 if current == med else math.copysign(float("inf"), current - med)
    return float(0.67448975 * (current - med) / mad)


def _rate_test(row: pd.Series, history: pd.DataFrame, metric: str) -> dict[str, Any]:
    num, den, _ = RATE_SPECS[metric]
    x, n = float(row.get(num, 0)), float(row.get(den, 0))
    hx, hn = float(history[num].sum()), float(history[den].sum())
    if n < 30 or hn <= 0:
        return {"z": None, "p_value": None, "baseline": None, "confidence_interval": wilson(x, n), "sufficient_n": False}
    p0 = hx / hn
    se = math.sqrt(max(p0 * (1 - p0) / n, 1e-12))
    z = (x / n - p0) / se
    return {"z": z, "p_value": float(2 * norm.sf(abs(z))), "baseline": p0,
            "confidence_interval": wilson(x, n), "sufficient_n": True}


def detect_anomalies(frame: pd.DataFrame, month: str, history_months: int = 12,
                     robust_threshold: float = 3.5, alpha: float = 0.05) -> list[dict[str, Any]]:
    f = frame.sort_values("purchase_month").reset_index(drop=True)
    idx = f.index[f["purchase_month"].eq(month)].tolist()
    if not idx:
        raise ValueError(f"Période indisponible : {month}")
    i = idx[0]
    history = f.iloc[max(0, i - history_months):i]
    row = f.iloc[i]
    results = []
    p_values: list[float] = []
    p_indices: list[int] = []
    for metric, (label, unit, direction) in METRIC_META.items():
        value = _finite(row.get(metric))
        rz = None if value is None else robust_z(history[metric], value)
        rate = _rate_test(row, history, metric) if metric in RATE_SPECS else None
        p = rate["p_value"] if rate else None
        result = {
            "metric_id": metric, "label": label, "unit": unit, "period": month, "value": value,
            "method": "two_proportion_normal" if rate else "robust_z_mad", "robust_z": rz,
            "p_value": p, "q_value": None, "baseline": rate["baseline"] if rate else _finite(history[metric].median()),
            "confidence_interval": list(rate["confidence_interval"]) if rate else None,
            "sample_size": int(row.get(RATE_SPECS[metric][1], 0)) if rate else len(history),
            "sufficient_history": len(history) >= 6, "sufficient_n": rate["sufficient_n"] if rate else len(history) >= 6,
            "direction": direction, "anomaly": False, "severity": "none", "evidence_id": f"om5:anomaly:{month}:{metric}",
        }
        if p is not None:
            p_indices.append(len(results)); p_values.append(p)
        results.append(result)
    if p_values:
        q_values = bh(np.asarray(p_values, dtype=float))
        for j, q in zip(p_indices, q_values):
            results[j]["q_value"] = float(q)
    for r in results:
        adverse = False
        if r["value"] is not None and r["baseline"] is not None:
            adverse = r["value"] > r["baseline"] if r["direction"] == "lower" else r["value"] < r["baseline"]
        significant = (r["q_value"] is not None and r["q_value"] < alpha) if r["method"].startswith("two_") else (
            r["robust_z"] is not None and abs(r["robust_z"]) >= robust_threshold)
        r["anomaly"] = bool(adverse and significant and r["sufficient_n"])
        magnitude = abs(r["robust_z"] or 0)
        r["severity"] = "high" if r["anomaly"] and magnitude >= 5 else "medium" if r["anomaly"] else "none"
    return results

