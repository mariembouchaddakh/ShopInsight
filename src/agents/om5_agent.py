"""OM5 autonomous KPI monitoring and multi-agent reporting workflow."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from .core import ESTIMATE, FACT, DataStore, Evidence, EvidenceLog, Line, Report, Tool, to_native
from .om5_anomalies import compare_periods as compare_frame, detect_anomalies
from .om5_kpis import METRIC_META, RATE_SPECS, available_months, monthly_kpis, seller_monitoring, trend_frame


Collaborator = Callable[[str, str, dict[str, Any]], tuple[Any, list[Evidence] | list[dict[str, Any]]]]


class ReportingAgent:
    """Deterministic planner whose branching depends on detected business signals.

    ``collaborator`` is an adapter around the existing BO1/BO2/BO3 public methods.
    It must perform one call at a time and return the result plus the evidence
    snapshot captured while the corresponding registry lock is held.
    """

    def __init__(self, project_dir: str | Path = ".", collaborator: Collaborator | None = None,
                 max_calls: int = 8, report_generator: Any | None = None) -> None:
        self.store = DataStore(project_dir)
        self.project_dir = Path(project_dir).resolve()
        self.collaborator = collaborator
        self.max_calls = max_calls
        self.log = EvidenceLog()
        self.trace: list[dict[str, Any]] = []
        self._seen: set[tuple[str, str]] = set()
        self.partial = False
        self.report_generator = report_generator
        from .om5_graph import build_om5_graph
        self.graph = build_om5_graph(self, report_generator)

    def default_month(self) -> str:
        return available_months(self.store)[-1]

    def _record(self, tool: str, args: dict[str, Any], fn: Callable[[], Any]) -> Any:
        key = (tool, repr(sorted(args.items())))
        if key in self._seen:
            self.trace.append({"tool": tool, "args": args, "status": "deduplicated", "reason": "appel identique déjà exécuté"})
            return None
        if len([x for x in self.trace if x.get("kind", "tool") == "tool" and x["status"] != "deduplicated"]) >= self.max_calls:
            self.partial = True
            self.trace.append({"tool": tool, "args": args, "status": "skipped", "reason": "budget d'appels atteint"})
            return None
        self._seen.add(key)
        t0 = time.perf_counter()
        try:
            result = fn()
            self.trace.append({"kind": "tool", "tool": tool, "args": args, "status": "ok", "duration_ms": round(1000 * (time.perf_counter() - t0), 1)})
            return result
        except Exception as exc:  # noqa: BLE001
            self.partial = True
            self.trace.append({"kind": "tool", "tool": tool, "args": args, "status": "error", "error": f"{type(exc).__name__}: {exc}",
                               "duration_ms": round(1000 * (time.perf_counter() - t0), 1)})
            return None

    def get_monthly_kpis(self, month: str, mode: str = "as_of") -> dict[str, Any]:
        values = monthly_kpis(self.store, month, mode)
        for value in values:
            self.log.add(value["evidence_id"], FACT, value["source"], value)
        seller_alerts = seller_monitoring(self.store, month)
        seller_eid = f"om5:sellers:{month}"
        self.log.add(seller_eid, ESTIMATE, "data/model/bo3_monthly_history.csv.gz", {"period": month, **seller_alerts})
        return {"month": month, "mode": mode, "kpis": values,
                "seller_alerts": {"evidence_id": seller_eid, **seller_alerts}}

    def get_trends(self, mode: str = "as_of") -> list[dict[str, Any]]:
        return to_native(trend_frame(self.store, mode).to_dict(orient="records"))

    def compare_periods(self, month: str, mode: str = "as_of") -> dict[str, Any]:
        rows = compare_frame(trend_frame(self.store, mode), month)
        eid = f"om5:comparison:{mode}:{month}"
        self.log.add(eid, ESTIMATE, "OM5 deterministic period comparison", {"period": month, "mode": mode, "comparisons": rows})
        return {"evidence_id": eid, "comparisons": rows}

    def detect_kpi_anomalies(self, month: str, mode: str = "as_of") -> dict[str, Any]:
        rows = detect_anomalies(trend_frame(self.store, mode), month)
        for row in rows:
            self.log.add(row["evidence_id"], ESTIMATE, "OM5 robust MAD / proportion test + Benjamini-Hochberg", row)
        return {"month": month, "mode": mode, "anomalies": rows,
                "method_note": "Taux: test de proportion avec effectif et correction BH; autres KPI: z robuste médiane/MAD."}

    def analyze_segments(self, month: str, metric: str, mode: str = "as_of", top_k: int = 8) -> dict[str, Any]:
        if metric not in METRIC_META:
            raise ValueError(f"KPI non segmentable : {metric}")
        if top_k < 1 or top_k > 50:
            raise ValueError("top_k doit être compris entre 1 et 50")
        results: dict[str, list[dict[str, Any]]] = {}
        for dimension, col in (("state", "customer_state"), ("category", "primary_category")):
            table = self._segment_frame(month, metric, col, mode)
            if table.empty:
                results[dimension] = []
                continue
            rows = table.sort_values(["contribution_abs", "sample_size"], ascending=False).head(top_k).to_dict(orient="records")
            results[dimension] = to_native(rows)
        eid = f"om5:segments:{mode}:{month}:{metric}"
        payload = {"period": month, "metric_id": metric, "mode": mode, "segments": results,
                   "caution": "Contributions descriptives; elles ne démontrent aucune causalité."}
        self.log.add(eid, ESTIMATE, "data/silver/orders_analysis.csv.gz", payload)
        return {"evidence_id": eid, **payload}

    def _segment_frame(self, month: str, metric: str, dimension: str, mode: str) -> pd.DataFrame:
        orders = self.store.orders.loc[self.store.orders["purchase_month"].eq(month)].copy()
        cutoff = pd.Period(month, "M").end_time.normalize() + pd.Timedelta(days=1)
        if metric in RATE_SPECS:
            if metric == "late_rate":
                known = pd.to_datetime(orders["order_delivered_customer_date"], errors="coerce").lt(cutoff) if mode == "as_of" else orders["late_label_eligible"].fillna(False)
                eligible, outcome = known & orders["late_label_eligible"].fillna(False), "is_late"
            elif metric in {"poor_review_rate", "written_comment_rate"}:
                known = pd.to_datetime(orders["review_answer_timestamp"], errors="coerce").lt(cutoff) if mode == "as_of" else orders["poor_review_label_eligible"].fillna(False)
                eligible = known & orders["poor_review_label_eligible"].fillna(False)
                outcome = "is_poor_review" if metric == "poor_review_rate" else "has_written_comment"
            else:
                known = pd.to_datetime(orders["order_delivered_carrier_date"], errors="coerce").lt(cutoff) if mode == "as_of" else orders["handover_label_eligible"].fillna(False)
                eligible, outcome = known & orders["handover_label_eligible"].fillna(False), "is_late_handover"
            g = orders.loc[eligible].groupby(dimension, dropna=False)[outcome].agg(["sum", "count"]).reset_index()
            g["value"] = g["sum"] / g["count"]
            g["sample_size"] = g["count"]
            global_rate = float(g["sum"].sum() / g["count"].sum()) if g["count"].sum() else np.nan
            g["contribution_abs"] = (g["sum"] - global_rate * g["count"]).abs()
            g["sufficient_n"] = g["count"] >= 30
        else:
            delivered_known = pd.to_datetime(orders["order_delivered_customer_date"], errors="coerce").lt(cutoff) if mode == "as_of" else orders["delivery_observed"].fillna(False)
            review_known = pd.to_datetime(orders["review_answer_timestamp"], errors="coerce").lt(cutoff) if mode == "as_of" else orders["review_score"].notna()
            if metric == "average_review_score":
                eligible = orders.loc[review_known]
                g = eligible.groupby(dimension, dropna=False)["review_score"].mean().rename("value").reset_index()
                sizes = eligible.groupby(dimension, dropna=False)["review_score"].count()
            elif metric == "reviewed_order_count":
                eligible = orders.loc[review_known]
                g = eligible.groupby(dimension, dropna=False)["order_id"].nunique().rename("value").reset_index()
                sizes = eligible.groupby(dimension, dropna=False)["order_id"].nunique()
            elif metric in {"delivery_duration_mean_days", "delivery_duration_median_days"}:
                eligible = orders.loc[delivered_known]
                agg = "mean" if metric.endswith("mean_days") else "median"
                g = eligible.groupby(dimension, dropna=False)["delivery_duration_days"].agg(agg).rename("value").reset_index()
                sizes = eligible.groupby(dimension, dropna=False)["delivery_duration_days"].count()
            elif metric == "delivered_order_count":
                eligible = orders.loc[delivered_known]
                g = eligible.groupby(dimension, dropna=False)["order_id"].nunique().rename("value").reset_index()
                sizes = eligible.groupby(dimension, dropna=False)["order_id"].nunique()
            elif metric == "average_item_value_per_order":
                g = orders.groupby(dimension, dropna=False)["item_price_total"].mean().rename("value").reset_index()
                sizes = orders.groupby(dimension, dropna=False)["order_id"].nunique()
            elif metric in {"item_price_total", "freight_total"}:
                g = orders.groupby(dimension, dropna=False)[metric].sum(min_count=1).rename("value").reset_index()
                sizes = orders.groupby(dimension, dropna=False)["order_id"].nunique()
            else:
                g = orders.groupby(dimension, dropna=False)["order_id"].nunique().rename("value").reset_index()
                sizes = orders.groupby(dimension, dropna=False)["order_id"].nunique()
            g["sample_size"] = g[dimension].map(sizes).astype(int)
            g["contribution_abs"] = g["value"].abs()
            g["sufficient_n"] = g["sample_size"] >= 30
        return g.rename(columns={dimension: "segment"})[["segment", "value", "sample_size", "contribution_abs", "sufficient_n"]]

    def _collect(self, agent: str, method: str, kwargs: dict[str, Any]) -> Any:
        if self.collaborator is None:
            raise RuntimeError("adaptateur multi-agent indisponible")
        result, evidence = self.collaborator(agent, method, kwargs)
        for raw in evidence:
            ev = raw if isinstance(raw, Evidence) else Evidence(**raw)
            namespaced = f"om5:{agent}:{ev.id}"
            self.log.add(namespaced, ev.kind, ev.source, {"original_id": ev.id, "agent": agent, "payload": ev.payload})
        eid = f"om5:{agent}:result:{method}:{kwargs.get('month', 'na')}"
        self.log.add(eid, ESTIMATE, f"{agent}.{method}", {"agent": agent, "method": method, "scope": kwargs, "result": to_native(result)})
        return {"evidence_id": eid, "result": to_native(result)}

    def prioritize_actions(self, anomalies: list[dict[str, Any]], segments: dict[str, Any]) -> list[dict[str, Any]]:
        actions = []
        playbook = {
            "late_rate": "Examiner les flux logistiques et contacter les vendeurs prioritaires; ne prendre aucune sanction automatique.",
            "poor_review_rate": "Analyser les thèmes des avis négatifs et vérifier les vendeurs/produits récurrents.",
            "order_count": "Vérifier les catégories et régions contribuant à la baisse d'activité.",
            "average_review_score": "Lire les avis récents et rapprocher les signaux logistiques et vendeurs.",
            "late_handover_rate": "Contrôler les délais de remise au transporteur avec les vendeurs concernés.",
        }
        for anomaly in anomalies:
            if not anomaly["anomaly"]:
                continue
            metric = anomaly["metric_id"]
            confidence = 1 - (anomaly["q_value"] if anomaly["q_value"] is not None else min(1.0, 1 / max(abs(anomaly["robust_z"] or 1), 1)))
            volume = min(1.0, (anomaly.get("sample_size") or 0) / 1000)
            magnitude = min(1.0, abs(anomaly.get("robust_z") or 3.5) / 6)
            score = round(100 * (0.45 * magnitude + 0.35 * confidence + 0.20 * volume), 1)
            actions.append({"metric_id": metric, "severity": anomaly["severity"], "priority_score": score,
                            "recommendation": playbook.get(metric, "Vérifier le signal avec les équipes métier avant toute décision."),
                            "justification": "Score heuristique explicable: 45% amplitude, 35% confiance, 20% volume.",
                            "evidence_id": anomaly["evidence_id"], "scope": "marketplace"})
        return sorted(actions, key=lambda x: x["priority_score"], reverse=True)

    def run(self, month: str | None = None, mode: str = "as_of", include_agents: bool = True) -> Report:
        self.log, self.trace, self._seen, self.partial = EvidenceLog(), [], set(), False
        month = month or self.default_month()
        if mode not in {"as_of", "retrospective"}:
            raise ValueError("mode doit être 'as_of' ou 'retrospective'")
        state = self.graph.invoke({"month": month, "mode": mode, "include_agents": include_agents,
                                   "retry_counter": 0, "partial": False, "generation_mode": "deterministic",
                                   "validation_errors": [], "fallback_used": False})
        return state["final_report"]

    def generation_context(self, state: dict[str, Any]) -> dict[str, Any]:
        """Compact evidence-grounded payload; never sends raw Olist tables."""
        tracked = {"order_count", "item_price_total", "late_rate", "poor_review_rate", "average_review_score",
                   "active_seller_count", "alerted_seller_count"}
        kpis = [{key: row.get(key) for key in ("metric_id", "label", "value", "unit", "numerator", "denominator",
                                                       "quality_status", "evidence_id")}
                for row in (state.get("kpi_values") or {}).get("kpis", []) if row["metric_id"] in tracked]
        comparison_block = state.get("historical_comparisons") or {}
        comparisons = [{**{key: row.get(key) for key in ("metric_id", "label", "unit", "value", "previous_period",
                                                                      "previous_value", "absolute_change", "relative_change_pct",
                                                                      "percentage_point_change", "year_over_year")},
                        "evidence_id": comparison_block.get("evidence_id")}
                       for row in comparison_block.get("comparisons", []) if row["metric_id"] in tracked]
        all_anomalies = state.get("detected_anomalies", [])
        active = [{key: row.get(key) for key in ("metric_id", "label", "value", "baseline", "method", "robust_z",
                                                          "q_value", "sample_size", "severity", "evidence_id")}
                  for row in all_anomalies if row.get("anomaly")]
        segments = {}
        for metric, block in state.get("segment_analysis", {}).items():
            segments[metric] = {"evidence_id": block["evidence_id"],
                                "state": block.get("segments", {}).get("state", [])[:3],
                                "category": block.get("segments", {}).get("category", [])[:3]}
        collaborators = {}
        for name in ("bo1", "bo2", "bo3"):
            block = state.get(f"{name}_results")
            if not block:
                continue
            result = block.get("result", {})
            if name in {"bo1", "bo2"}:
                collaborators[name] = {"evidence_id": block["evidence_id"], "title": result.get("title"),
                                       "summary": result.get("narrative"),
                                       "key_findings": [x.get("text") for x in (result.get("facts", []) + result.get("estimates", []))[:4]]}
            else:
                alerts = result.get("alerts", {})
                collaborators[name] = {"evidence_id": block["evidence_id"], "overview": result.get("overview", {}),
                                       "alert_count": alerts.get("n_alerts"), "alerted_sellers": alerts.get("n_alerted_sellers"),
                                       "top_sellers": [x.get("seller_id") for x in alerts.get("listing", [])[:3]],
                                       "category_summary": result.get("categories", {}).get("categories_with_most_alerted_sellers", [])[:3]}
        collaborator_refs = [x["evidence_id"] for x in collaborators.values()]
        slots = [{"metric_id": x["metric_id"], "priority_score": x["priority_score"], "severity": x["severity"],
                  "evidence_ids": [x["evidence_id"], *collaborator_refs]} for x in state.get("priority_scores", [])]
        if not slots and all_anomalies:
            slots = [{"metric_id": "none", "priority_score": 0, "severity": "none",
                      "evidence_ids": [x["evidence_id"] for x in all_anomalies[:3]]}]
        allowed = {x["evidence_id"] for x in kpis}
        allowed.update(x["evidence_id"] for x in active)
        allowed.update(x["evidence_id"] for x in all_anomalies[:3] if not active)
        if comparison_block.get("evidence_id"):
            allowed.add(comparison_block["evidence_id"])
        allowed.update(x["evidence_id"] for x in segments.values())
        allowed.update(x["evidence_id"] for x in collaborators.values())
        return to_native({
            "period": state["month"], "temporal_mode": state["mode"],
            "historical_dataset": "Olist 2016-2018; replay historique, pas temps réel",
            "kpis": kpis, "comparisons": comparisons,
            "anomaly_status": "detected" if active else "none_detected", "active_anomalies": active,
            "segments": segments, "collaborators": collaborators, "recommendation_slots": slots,
            "allowed_evidence_ids": sorted(allowed),
            "limitations": ["corrélation non causale", "données historiques", "rapport partiel" if self.partial else "rapport analytique complet"],
        })

    def _report(self, month: str, mode: str, kpis: dict[str, Any] | None, comparisons: dict[str, Any] | None,
                anomalies: list[dict[str, Any]], segments: dict[str, Any], insights: dict[str, Any],
                actions: list[dict[str, Any]]) -> Report:
        rep = Report(title=f"OM5 — Pilotage marketplace {month}")
        rep.narrative = "Rapport déterministe fondé sur les données Olist historiques et les preuves ci-dessous."
        if kpis:
            by_id = {x["metric_id"]: x for x in kpis["kpis"]}
            for metric in ("order_count", "item_price_total", "late_rate", "poor_review_rate", "average_review_score", "active_seller_count", "alerted_seller_count"):
                x = by_id[metric]
                if x["value"] is None:
                    continue
                value = "indisponible" if x["value"] is None else f"{x['value']:.3f}".rstrip("0").rstrip(".")
                rep.facts.append(Line(f"{x['label']} : {value} {x['unit']} ({x['mode']}, qualité {x['quality_status']}).", [x["evidence_id"]]))
        active = [x for x in anomalies if x["anomaly"]]
        if active:
            for x in active:
                rep.estimates.append(Line(f"Anomalie {x['severity']} détectée sur {x['label']} par {x['method']}.", [x["evidence_id"]]))
        elif anomalies:
            first = anomalies[0]["evidence_id"]
            rep.estimates.append(Line("Aucune dégradation statistiquement signalée; le rapport standard suffit.", [first]))
        for metric, seg in segments.items():
            rep.estimates.append(Line(f"Segments analysés pour {METRIC_META[metric][0]}; contributions descriptives, sans causalité démontrée.", [seg["evidence_id"]]))
        for agent, insight in insights.items():
            rep.estimates.append(Line(f"Conclusion complémentaire collectée auprès de {agent.upper()} dans le même périmètre mensuel.", [insight["evidence_id"]]))
        for action in actions:
            rep.actions.append(Line(action["recommendation"], [action["evidence_id"]]))
        if not actions:
            rep.actions.append(Line("Poursuivre la surveillance mensuelle; aucune intervention exceptionnelle n'est justifiée par les détecteurs.",
                                    [anomalies[0]["evidence_id"]] if anomalies else []))
        rep.caveats = [
            "Olist couvre 2016–2018 : le replay mensuel n'est pas un suivi temps réel.",
            "Les anomalies sont des signaux d'investigation, pas des preuves de causalité.",
            "La valeur des articles n'est ni le chiffre d'affaires net ni le bénéfice d'Olist.",
        ]
        return rep

    def tools(self) -> list[Tool]:
        return [
            Tool("get_monthly_kpis", "KPI marketplace sourcés", {"type": "object", "properties": {"month": {"type": "string"}, "mode": {"enum": ["as_of", "retrospective"]}}, "required": ["month"]}, self.get_monthly_kpis),
            Tool("compare_periods", "Comparaisons temporelles", {"type": "object", "properties": {"month": {"type": "string"}, "mode": {"enum": ["as_of", "retrospective"]}}, "required": ["month"]}, self.compare_periods),
            Tool("detect_kpi_anomalies", "Détection statistique", {"type": "object", "properties": {"month": {"type": "string"}, "mode": {"enum": ["as_of", "retrospective"]}}, "required": ["month"]}, self.detect_kpi_anomalies),
            Tool("analyze_segments", "Contributions par État et catégorie", {"type": "object", "properties": {"month": {"type": "string"}, "metric": {"type": "string"}, "mode": {"enum": ["as_of", "retrospective"]}}, "required": ["month", "metric"]}, self.analyze_segments),
        ]

