"""BO4 delivery-duration intervals with chronological, leakage-safe inference."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

ARTIFACT = "data/model/bo4_eta.joblib"


def _ts(x: Any) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_localize(None) if t.tzinfo else t


def repair_quantiles(p10: float, p50: float, p90: float) -> tuple[float, float, float]:
    """Clip impossible durations and enforce monotone quantiles."""
    a = np.maximum.accumulate(np.maximum([p10, p50, p90], 0.0))
    return tuple(float(x) for x in a)


def interval_metrics(y: np.ndarray, lo: np.ndarray, med: np.ndarray, hi: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import mean_absolute_error, mean_pinball_loss, mean_squared_error
    width = hi - lo
    alpha = .2
    winkler = width + (2 / alpha) * (lo - y) * (y < lo) + (2 / alpha) * (y - hi) * (y > hi)
    return {
        "mae": float(mean_absolute_error(y, med)), "rmse": float(mean_squared_error(y, med) ** .5),
        "pinball_p10": float(mean_pinball_loss(y, lo, alpha=.1)),
        "pinball_p50": float(mean_pinball_loss(y, med, alpha=.5)),
        "pinball_p90": float(mean_pinball_loss(y, hi, alpha=.9)),
        "picp": float(np.mean((y >= lo) & (y <= hi))), "mpiw": float(np.mean(width)),
        "winkler": float(np.mean(winkler)),
    }


@dataclass
class DeliveryIntervalModel:
    models: dict[str, Any]
    features: list[str]
    calibration: float = 0.0
    name: str = "unknown"

    def predict_frame(self, frame: pd.DataFrame) -> np.ndarray:
        raw = np.column_stack([self.models[q].predict(frame[self.features]) for q in ("p10", "p50", "p90")])
        raw[:, 0] -= self.calibration
        raw[:, 2] += self.calibration
        return np.asarray([repair_quantiles(*r) for r in raw])

    def predict_one(self, row: pd.DataFrame) -> dict[str, float]:
        p10, p50, p90 = self.predict_frame(row)[0]
        return {"p10_days": p10, "p50_days": p50, "p90_days": p90, "target_coverage": .8,
                "calibration_days": self.calibration, "model": self.name}

    @classmethod
    def load(cls, project_dir: str | Path) -> "DeliveryIntervalModel":
        path = Path(project_dir) / ARTIFACT
        if not path.exists():
            raise FileNotFoundError(f"{ARTIFACT} introuvable : lancez python src/train_bo4_models.py --project-dir .")
        return joblib.load(path)


@dataclass
class EmpiricalIntervalModel:
    global_q: tuple[float, float, float]
    regional_q: dict[str, tuple[float, float, float]] | None = None
    calibration: float = 0.0
    name: str = "global_empirical"

    def predict_frame(self, frame: pd.DataFrame) -> np.ndarray:
        rows = []
        for _, r in frame.iterrows():
            q = (self.regional_q or {}).get(str(r.get("customer_state")), self.global_q)
            rows.append(repair_quantiles(q[0] - self.calibration, q[1], q[2] + self.calibration))
        return np.asarray(rows)

    def predict_one(self, row: pd.DataFrame) -> dict[str, float]:
        p10, p50, p90 = self.predict_frame(row)[0]
        return {"p10_days": p10, "p50_days": p50, "p90_days": p90, "target_coverage": .8,
                "calibration_days": self.calibration, "model": self.name}


def approval_time_frame(project_dir: str | Path) -> pd.DataFrame:
    """Join existing features to targets, excluding BO1/2 target encodings.

    Those encodings use shuffled OOF folds and are temporally unsafe for BO4.
    """
    root = Path(project_dir)
    parts = [pd.read_csv(root / f"data/model/features_{s}.csv.gz", parse_dates=["order_purchase_timestamp"]).assign(source_split=s)
             for s in ("train", "valid", "test")]
    f = pd.concat(parts, ignore_index=True)
    unsafe = [c for c in f if c.startswith("te_") or c in {"is_late", "is_poor_review", "late_label_eligible", "poor_review_label_eligible", "split"}]
    f = f.drop(columns=unsafe, errors="ignore")
    use = ["order_id", "delivery_duration_days", "order_delivered_customer_date", "order_status", "customer_state",
           "primary_category", "order_estimated_delivery_date", "order_approved_at", "review_answer_timestamp"]
    o = pd.read_csv(root / "data/silver/orders_analysis.csv.gz", usecols=lambda c: c in use, low_memory=False)
    for c in [x for x in use if x.endswith("date") or x.endswith("_at") or x.endswith("timestamp")]:
        if c in o: o[c] = pd.to_datetime(o[c], errors="coerce", format="mixed")
    return f.merge(o, on="order_id", how="left", validate="one_to_one")


def save_results(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
