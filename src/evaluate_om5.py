"""Reproducible evaluation of OM5 on authentic Olist data.

Historical data has no independent anomaly labels.  Therefore supervised detector
metrics are reported only for explicitly labelled perturbation simulations, never
as real-world ground truth.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.core import DataStore  # noqa: E402
from agents.om5_agent import ReportingAgent  # noqa: E402
from agents.om5_anomalies import detect_anomalies  # noqa: E402
from agents.om5_kpis import monthly_kpis, trend_frame  # noqa: E402


TEST_MONTHS = ["2018-04", "2018-05", "2018-06"]


def kpi_validation(store: DataStore) -> dict:
    checks = []
    for month in store.monthly.loc[store.monthly["is_complete_period"].astype(bool), "purchase_month"].astype(str):
        got = {x["metric_id"]: x for x in monthly_kpis(store, month, "retrospective")}
        expected = store.monthly.loc[store.monthly["purchase_month"].eq(month)].iloc[0]
        for metric in ("order_count", "late_rate", "poor_review_rate", "average_review_score", "item_price_total", "freight_total"):
            a, b = got[metric]["value"], expected[metric]
            checks.append(bool((a is None and pd.isna(b)) or np.isclose(float(a), float(b), equal_nan=True)))
    orders = store.orders.copy()
    base = {x["metric_id"]: x["value"] for x in monthly_kpis(store, "2018-03", "as_of")}
    cutoff = pd.Timestamp("2018-04-01")
    future_cols = ["order_delivered_customer_date", "order_delivered_carrier_date", "review_answer_timestamp"]
    truncated = orders.copy()
    for col in future_cols:
        ts = pd.to_datetime(truncated[col], errors="coerce")
        truncated.loc[ts >= cutoff, col] = pd.NaT
    alt_store = DataStore(store.dir)
    alt_store._cache["orders"] = truncated
    after = {x["metric_id"]: x["value"] for x in monthly_kpis(alt_store, "2018-03", "as_of")}
    invariant_metrics = ["order_count", "late_rate", "poor_review_rate", "late_handover_rate", "average_review_score"]
    temporal = all((base[m] is None and after[m] is None) or np.isclose(base[m], after[m], equal_nan=True) for m in invariant_metrics)
    return {"gold_concordance_checks": len(checks), "gold_concordance_passed": int(sum(checks)),
            "gold_concordance_rate": float(np.mean(checks)), "temporal_invariance_after_future_suppression": temporal,
            "zero_denominator_returns_null": all(x["value"] is None for x in monthly_kpis(store, "2016-11", "as_of") if x["metric_id"] in {"late_rate", "poor_review_rate"})}


def detector_evaluation(store: DataStore) -> dict:
    base = trend_frame(store, "as_of")
    historical = []
    for month in TEST_MONTHS:
        historical.extend(x for x in detect_anomalies(base, month) if x["anomaly"])
    false_alert_rate = len(historical) / (len(TEST_MONTHS) * 13)
    trials = []
    for seed in (11, 29, 47):
        rng = np.random.default_rng(seed)
        for month in TEST_MONTHS:
            for delta in (.05, .10, .20):
                f = base.copy()
                i = f.index[f["purchase_month"].eq(month)][0]
                n = int(f.loc[i, "late_eligible_count"])
                target_rate = min(.99, float(f.loc[i, "late_rate"]) + delta)
                injected = int(rng.binomial(n, target_rate))
                f.loc[i, "late_order_count"] = injected
                f.loc[i, "late_rate"] = injected / n
                robust = next(x for x in detect_anomalies(f, month) if x["metric_id"] == "late_rate")["anomaly"]
                hist = f.loc[f["purchase_month"].lt(month)].tail(6)["late_rate"].median()
                baseline = bool(f.loc[i, "late_rate"] > 1.5 * hist)
                trials.append({"seed": seed, "month": month, "delta_pp": int(delta * 100), "robust_detected": robust, "baseline_detected": baseline})
    by_delta = {}
    for delta, g in pd.DataFrame(trials).groupby("delta_pp"):
        control_robust, control_baseline = [], []
        for _seed in (11, 29, 47):
            for month in TEST_MONTHS:
                control_robust.append(next(x for x in detect_anomalies(base, month) if x["metric_id"] == "late_rate")["anomaly"])
                i = base.index[base["purchase_month"].eq(month)][0]
                hist = base.loc[base["purchase_month"].lt(month)].tail(6)["late_rate"].median()
                control_baseline.append(bool(base.loc[i, "late_rate"] > 1.5 * hist))

        def scores(positive: pd.Series, negative: list[bool]) -> dict:
            tp, fn, fp, tn = int(positive.sum()), int((~positive).sum()), int(sum(negative)), int(len(negative) - sum(negative))
            precision = tp / (tp + fp) if tp + fp else 0.0
            recall = tp / (tp + fn) if tp + fn else 0.0
            return {"precision": precision, "recall": recall,
                    "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
                    "false_alert_rate": fp / (fp + tn) if fp + tn else 0.0}

        by_delta[str(delta)] = {"positive_trials": int(len(g)), "negative_controls": len(control_robust),
                                "robust": scores(g["robust_detected"].astype(bool), control_robust),
                                "simple_threshold": scores(g["baseline_detected"].astype(bool), control_baseline)}
    return {"real_history": {"ground_truth_available": False, "unlabelled_alerts": len(historical),
                             "alert_rate_per_metric_month": false_alert_rate,
                             "note": "Taux d'alertes descriptif, pas un faux-positif mesurable sans vérité terrain."},
            "simulation": {"label": "anomalies injectées, non observations réelles", "trials": len(trials), "rates_by_delta_pp": by_delta}}


def agent_evaluation(root: Path) -> dict:
    agent = ReportingAgent(root, max_calls=8)
    t0 = time.perf_counter(); anomaly_report = agent.run("2018-03", "as_of", False); latency = time.perf_counter() - t0
    anomaly_tools = [x["tool"] for x in anomaly_report.meta["tool_trace"] if x["status"] == "ok"]
    no_signal = agent.run("2018-06", "as_of", False)

    def unavailable(name, method, kwargs):
        raise RuntimeError(f"{name} indisponible pour scénario de robustesse")
    degraded = ReportingAgent(root, collaborator=unavailable, max_calls=8).run("2018-03", "as_of", True)
    return {"scenarios": {
        "degradation_2018_03": {"expected_segment_analysis": True, "passed": "analyze_segments" in anomaly_tools,
                                "evidence_valid": anomaly_report.meta["evidence_valid"], "calls": anomaly_report.meta["calls_used"]},
        "standard_2018_06": {"unnecessary_external_calls": sum(x["tool"].startswith("collect_") for x in no_signal.meta["tool_trace"]),
                             "within_budget": no_signal.meta["calls_used"] <= 8},
        "agents_unavailable": {"partial_report": degraded.meta["partial"], "evidence_valid": degraded.meta["evidence_valid"],
                               "errors_captured": sum(x["status"] == "error" for x in degraded.meta["tool_trace"])}},
        "latency_seconds_cold": round(latency, 3), "works_without_llm": True,
        "citation_accuracy": float(anomaly_report.meta["evidence_valid"]),
        "ablation": {
            "kpi_only": {"components": ["KPI"], "agent_calls": 0},
            "kpi_detection": {"components": ["KPI", "détection"], "detected_2018_03": sum(x["anomaly"] for x in anomaly_report.meta["anomalies"])},
            "dynamic_agents": {"components": ["KPI", "détection", "planification"], "planned_tools": anomaly_tools},
            "validated_llm": {"executed": False, "reason": "Aucune clé API requise ni utilisée; fallback déterministe évalué."},
        }}


def write_report(root: Path, evaluation: dict, benchmark: dict) -> None:
    q = root / "quality"; q.mkdir(exist_ok=True)
    (q / "om5_evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
    (q / "om5_benchmark.json").write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")
    rates = evaluation["detectors"]["simulation"]["rates_by_delta_pp"]
    rows = "\n".join(f"| +{d} pp | {v['positive_trials']} | {v['simple_threshold']['precision']:.3f} | {v['simple_threshold']['recall']:.3f} | {v['simple_threshold']['f1']:.3f} | {v['robust']['precision']:.3f} | {v['robust']['recall']:.3f} | {v['robust']['f1']:.3f} |" for d, v in rates.items())
    k = evaluation["kpis"]; a = evaluation["agent"]
    md = f"""# Évaluation OM5 — données Olist authentiques

## Périmètre

Le pipeline est évalué sur les 99 441 commandes Olist. Les mois TEST 2018-04 à 2018-06 sont réservés à la lecture finale. Olist ne fournit aucune vérité terrain d'anomalie KPI : les métriques supervisées ci-dessous concernent uniquement des perturbations injectées et reproductibles.

## Validation des KPI

- Concordance Gold : {k['gold_concordance_passed']}/{k['gold_concordance_checks']} ({k['gold_concordance_rate']:.1%}).
- Invariance après suppression des événements futurs : {k['temporal_invariance_after_future_suppression']}.
- Division par zéro → valeur nulle : {k['zero_denominator_returns_null']}.

## Détecteurs — simulation séparée des observations

| Amplitude injectée | Essais positifs | Précision baseline | Rappel baseline | F1 baseline | Précision OM5 | Rappel OM5 | F1 OM5 |
|---:|---:|---:|---:|---:|---:|---:|---:|
{rows}

Le taux d'alertes sur l'historique non étiqueté est descriptif et ne doit pas être nommé taux de faux positifs. Les simulations modifient les compteurs du taux de retard sur plusieurs mois, amplitudes et graines.

## Évaluation agentique

- Citations valides : {a['citation_accuracy']:.0%}.
- Fonctionnement sans LLM : {a['works_without_llm']}.
- Latence froide du scénario mars 2018 : {a['latency_seconds_cold']:.3f} s.
- Agent indisponible : rapport partiel conservé et erreurs tracées ({a['scenarios']['agents_unavailable']['errors_captured']}).

## Limites

- Seulement 21 mois complets : une méthode robuste et parcimonieuse est préférable aux modèles temporels complexes.
- Les injections testent la sensibilité, pas la validité causale des alertes historiques.
- L'ablation LLM n'est pas exécutée sans clé; OM5 reste intégralement déterministe.
"""
    (q / "om5_evaluation_report.md").write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", type=Path, default=Path("."))
    args = parser.parse_args(); root = args.project_dir.resolve(); store = DataStore(root)
    evaluation = {"dataset": {"name": "Brazilian E-Commerce Public Dataset by Olist", "authentic": True,
                              "orders": int(len(store.orders)), "complete_months": int(store.monthly["is_complete_period"].sum()),
                              "train": "2016-10..2017-12", "validation": "2018-01..2018-03", "test": TEST_MONTHS},
                  "kpis": kpi_validation(store), "detectors": detector_evaluation(store), "agent": agent_evaluation(root)}
    benchmark = {"selection_rule_pre_test": "Paramètres fixés a priori; à sensibilité comparable, préférer la méthode qui utilise les dénominateurs, contrôle les comparaisons multiples et expose l'incertitude.",
                 "selected": "tests de proportion + BH pour taux; MAD robuste pour KPI continus", "test_months": TEST_MONTHS,
                 "test_read_once_by_this_script": True, "results": evaluation["detectors"]}
    write_report(root, evaluation, benchmark)
    print(json.dumps({"quality_files": ["quality/om5_evaluation.json", "quality/om5_benchmark.json", "quality/om5_evaluation_report.md"],
                      "kpi_validation": evaluation["kpis"], "detector_simulation": evaluation["detectors"]["simulation"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

