"""Train and benchmark BO4 P10/P50/P90 models without opening the test set early."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agents.bo4_eta import ARTIFACT, DeliveryIntervalModel, EmpiricalIntervalModel, approval_time_frame, interval_metrics, save_results


def pipe(frame: pd.DataFrame, quantile: float, kind: str):
    cats = [c for c in ("customer_state", "primary_category") if c in frame]
    nums = [c for c in frame if c not in cats and pd.api.types.is_numeric_dtype(frame[c])]
    prep = ColumnTransformer([("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), nums),
                              ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=10), cats)])
    if kind == "gradient_boosting":
        reg = GradientBoostingRegressor(loss="quantile", alpha=quantile, n_estimators=180, max_depth=3,
                                        learning_rate=.04, min_samples_leaf=20, random_state=42)
    elif kind == "lightgbm":
        try:
            from lightgbm import LGBMRegressor
        except ImportError as e:
            raise RuntimeError("LightGBM absent; installez requirements-bo4.txt") from e
        reg = LGBMRegressor(objective="quantile", alpha=quantile, n_estimators=350, learning_rate=.035,
                            num_leaves=31, min_child_samples=30, random_state=42, verbosity=-1)
    else:
        from sklearn.linear_model import QuantileRegressor
        reg = QuantileRegressor(quantile=quantile, alpha=.001, solver="highs")
    return Pipeline([("prep", prep), ("model", reg)]), nums + cats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", type=Path, default=Path("."))
    ap.add_argument("--linear-max-rows", type=int, default=12000,
                    help="Deterministic chronological sample for the exact linear-programming baseline")
    ap.add_argument("--refresh", action="store_true", help="Ignore resumable model checkpoints")
    a = ap.parse_args()
    root = a.project_dir.resolve(); d = approval_time_frame(root)
    d = d[d.delivery_duration_days.notna() & (d.delivery_duration_days >= 0)].copy()
    # The outcome must have become observable before each fitting cutoff.
    train = d[(d.order_purchase_timestamp >= "2016-10-01") & (d.order_purchase_timestamp < "2018-01-01") & (d.order_delivered_customer_date < "2018-01-01")]
    tune = d[(d.order_purchase_timestamp >= "2018-01-01") & (d.order_purchase_timestamp < "2018-03-01") & (d.order_delivered_customer_date < "2018-03-01")]
    cal = d[(d.order_purchase_timestamp >= "2018-03-01") & (d.order_purchase_timestamp < "2018-04-01") & (d.order_delivered_customer_date < "2018-04-01")]
    test = d[(d.order_purchase_timestamp >= "2018-04-01") & (d.order_purchase_timestamp < "2018-09-01")]
    ycol = "delivery_duration_days"; drop = {ycol, "order_id", "order_purchase_timestamp", "source_split", "order_delivered_customer_date",
                                             "order_status", "order_estimated_delivery_date", "order_approved_at", "review_answer_timestamp"}
    Xcols = [c for c in d.columns if c not in drop and not c.startswith("te_")]
    cache = root / "data/model/bo4_training_cache"; cache.mkdir(parents=True, exist_ok=True)
    candidates = {}; fitted = {}
    gq = tuple(train[ycol].quantile([.1,.5,.9]).to_numpy())
    fitted["global_empirical"] = EmpiricalIntervalModel(gq)
    rq = {str(k): tuple(v[ycol].quantile([.1,.5,.9]).to_numpy()) for k,v in train.groupby("customer_state") if len(v)>=100}
    fitted["regional_empirical"] = EmpiricalIntervalModel(gq, rq, name="regional_empirical")
    for kind in ("global_empirical", "regional_empirical"):
        bp=fitted[kind].predict_frame(tune);candidates[kind]=interval_metrics(tune[ycol].to_numpy(),bp[:,0],bp[:,1],bp[:,2])
    for kind in ("linear", "gradient_boosting", "lightgbm"):
        try:
            checkpoint = cache / f"selection_{kind}.joblib"
            fit_train = train
            if kind == "linear" and len(train) > a.linear_max_rows:
                idx = np.linspace(0, len(train) - 1, a.linear_max_rows, dtype=int)
                fit_train = train.sort_values("order_purchase_timestamp").iloc[idx]
            if checkpoint.exists() and not a.refresh:
                print(f"[{kind}] reprise du checkpoint {checkpoint.name}", flush=True)
                obj = joblib.load(checkpoint)
            else:
                print(f"[{kind}] entraînement sur {len(fit_train)} lignes", flush=True)
                models = {}; features = None
                for q, alpha in (("p10", .1), ("p50", .5), ("p90", .9)):
                    started=time.time(); print(f"  {q}…", flush=True)
                    m, features = pipe(fit_train[Xcols], alpha, kind); m.fit(fit_train[Xcols], fit_train[ycol]); models[q] = m
                    print(f"  {q} terminé en {(time.time()-started)/60:.1f} min", flush=True)
                obj = DeliveryIntervalModel(models, Xcols, name=kind); joblib.dump(obj, checkpoint)
            pred = obj.predict_frame(tune)
            candidates[kind] = interval_metrics(tune[ycol].to_numpy(), pred[:, 0], pred[:, 1], pred[:, 2]); fitted[kind] = obj
            candidates[kind]["fit_rows"] = int(len(fit_train))
        except RuntimeError as e:
            candidates[kind] = {"status": "skipped", "reason": str(e)}
    eligible = {k: v for k, v in candidates.items() if "mae" in v}
    selected = min(eligible, key=lambda k: eligible[k]["winkler"] + 20 * abs(eligible[k]["picp"] - .8))
    final = fitted[selected]
    # Refit the chosen learned family with all outcomes observable by 1 March;
    # March remains a disjoint conformal calibration window.
    if selected in ("linear", "gradient_boosting", "lightgbm"):
        fit=pd.concat([train,tune],ignore_index=True).sort_values("order_purchase_timestamp")
        if selected == "linear" and len(fit) > a.linear_max_rows:
            fit=fit.iloc[np.linspace(0,len(fit)-1,a.linear_max_rows,dtype=int)]
        checkpoint=cache/f"final_{selected}.joblib"
        if checkpoint.exists() and not a.refresh:
            print(f"[final] reprise de {checkpoint.name}",flush=True);final=joblib.load(checkpoint)
        else:
            print(f"[final] réentraînement {selected} sur {len(fit)} lignes",flush=True);models={}
            for q,alpha in (("p10",.1),("p50",.5),("p90",.9)):
                started=time.time();print(f"  {q}…",flush=True)
                m,_=pipe(fit[Xcols],alpha,selected);m.fit(fit[Xcols],fit[ycol]);models[q]=m
                print(f"  {q} terminé en {(time.time()-started)/60:.1f} min",flush=True)
            final=DeliveryIntervalModel(models,Xcols,name=selected);joblib.dump(final,checkpoint)
    cp = final.predict_frame(cal); scores = np.maximum(cp[:, 0] - cal[ycol].to_numpy(), cal[ycol].to_numpy() - cp[:, 2])
    final.calibration = float(max(0, np.quantile(scores, min(1, np.ceil((len(scores) + 1) * .8) / len(scores)), method="higher")))
    tp = final.predict_frame(test); test_metrics = interval_metrics(test[ycol].to_numpy(), tp[:, 0], tp[:, 1], tp[:, 2])
    out = root / ARTIFACT; out.parent.mkdir(parents=True, exist_ok=True); joblib.dump(final, out)
    promise_days=(pd.to_datetime(test.order_estimated_delivery_date)-pd.to_datetime(test.order_purchase_timestamp)).dt.total_seconds().to_numpy()/86400
    promise={"mae":float(np.mean(np.abs(test[ycol].to_numpy()-promise_days))),"rmse":float(np.mean((test[ycol].to_numpy()-promise_days)**2)**.5),
             "delivered_by_promise_rate":float(np.mean(test[ycol].to_numpy()<=promise_days))}
    groups={}
    eval_frame=test.assign(_lo=tp[:,0],_med=tp[:,1],_hi=tp[:,2],_month=test.order_purchase_timestamp.dt.to_period("M").astype(str))
    for key in ("_month","customer_state","seller_count"):
        if key not in eval_frame: continue
        groups[key]={str(v):interval_metrics(g[ycol].to_numpy(),g._lo.to_numpy(),g._med.to_numpy(),g._hi.to_numpy()) for v,g in eval_frame.groupby(key) if len(g)>=20}
    save_results(root / "quality/bo4_model_results.json", {"status": "evaluated", "selection_split": candidates, "selected": selected,
                 "calibration_days": final.calibration, "test": test_metrics, "n": {"train": len(train), "tune": len(tune), "calibration": len(cal), "test": len(test)},
                 "original_marketplace_promise":promise,"test_slices":groups,
                 "linear_baseline_sampling": {"max_rows": a.linear_max_rows, "method": "evenly_spaced_chronological"},
                 "leakage_audit": "BO1/BO2 shuffled target encodings excluded; outcomes constrained by fitting cutoff."})
    print(f"BO4 sélectionné: {selected}; résultats: {root / 'quality/bo4_model_results.json'}", flush=True)


if __name__ == "__main__": main()
