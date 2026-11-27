"""Real LangGraph orchestration for OM5.

The graph owns routing only. KPI computation, statistical detection, planning and
priority scoring remain deterministic methods of :class:`ReportingAgent`.
"""
from __future__ import annotations

import time
from dataclasses import asdict
from typing import TYPE_CHECKING, Any, Protocol

from langgraph.graph import END, START, StateGraph

from .core import Line, Report
from .om5_state import OM5State
from .om5_validation import validate_generated_report, validate_report

if TYPE_CHECKING:
    from .om5_agent import ReportingAgent


class ReportGenerator(Protocol):
    provider: str
    model: str

    def generate(self, context: dict[str, Any], validation_errors: list[str] | None = None) -> tuple[dict[str, Any], float]: ...


def _node(agent: "ReportingAgent", name: str, fn):
    def wrapped(state: OM5State) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            update = fn(state)
            agent.trace.append({"kind": "node", "tool": name, "status": "ok", "duration_ms": round(1000 * (time.perf_counter() - t0), 1)})
            return update
        except Exception as exc:  # graph must always reach a usable report
            if name != "gemini_generation":
                agent.partial = True
            agent.trace.append({"kind": "node", "tool": name, "status": "error", "error": f"{type(exc).__name__}: {exc}",
                                "duration_ms": round(1000 * (time.perf_counter() - t0), 1)})
            if name == "gemini_generation":
                return {"generated_report": None, "fallback_reason": f"{type(exc).__name__}: {exc}", "validation_errors": [str(exc)],
                        "llm_provider": getattr(agent.report_generator, "provider", None),
                        "llm_model": getattr(agent.report_generator, "model", None)}
            raise
    return wrapped


def build_om5_graph(agent: "ReportingAgent", generator: ReportGenerator | None = None):
    def kpi(state: OM5State):
        value = agent._record("get_monthly_kpis", {"month": state["month"], "mode": state["mode"]},
                              lambda: agent.get_monthly_kpis(state["month"], state["mode"]))
        return {"kpi_values": value}

    def comparisons(state: OM5State):
        value = agent._record("compare_periods", {"month": state["month"], "mode": state["mode"]},
                              lambda: agent.compare_periods(state["month"], state["mode"]))
        return {"historical_comparisons": value}

    def anomalies(state: OM5State):
        value = agent._record("detect_kpi_anomalies", {"month": state["month"], "mode": state["mode"]},
                              lambda: agent.detect_kpi_anomalies(state["month"], state["mode"]))
        rows = (value or {}).get("anomalies", [])
        return {"detected_anomalies": rows, "active_business_signals": [x for x in rows if x.get("anomaly")]}

    def route(state: OM5State) -> str:
        return "segments" if state.get("active_business_signals") else "consolidation"

    def segments(state: OM5State):
        results: dict[str, Any] = {}
        for anomaly in state.get("active_business_signals", [])[:2]:
            metric = anomaly["metric_id"]
            result = agent._record("analyze_segments", {"month": state["month"], "metric": metric, "mode": state["mode"]},
                                   lambda metric=metric: agent.analyze_segments(state["month"], metric, state["mode"]))
            if result:
                results[metric] = result
        return {"segment_analysis": results}

    def planner(state: OM5State):
        bad = {x["metric_id"] for x in state.get("active_business_signals", [])}
        plan: list[dict[str, Any]] = []
        if state.get("include_agents"):
            if bad & {"late_rate", "late_handover_rate", "delivery_duration_mean_days"}:
                plan.append({"agent": "bo1", "method": "triage", "kwargs": {"period": state["month"], "top_k": 10, "audit": False}, "reason": "signal logistique"})
            if bad & {"late_rate", "poor_review_rate", "average_review_score"}:
                plan.append({"agent": "bo2", "method": "report", "kwargs": {"month": state["month"], "focus": "livraison" if "late_rate" in bad else None, "use_llm": False}, "reason": "signal client"})
            if bad & {"late_rate", "poor_review_rate", "late_handover_rate"}:
                plan.append({"agent": "bo3", "method": "marketplace_brief", "kwargs": {"month": state["month"], "top_k": 10}, "reason": "signal vendeur"})
        return {"investigation_plan": plan}

    def execute(state: OM5State):
        update: dict[str, Any] = {}
        for item in state.get("investigation_plan", []):
            name, method, kwargs = item["agent"], item["method"], item["kwargs"]
            result = agent._record(f"collect_{name}_insights", {"method": method, **kwargs, "reason": item["reason"]},
                                   lambda name=name, method=method, kwargs=kwargs: agent._collect(name, method, kwargs))
            update[f"{name}_results"] = result
        return update

    def consolidation(state: OM5State):
        insights = {name: state.get(f"{name}_results") for name in ("bo1", "bo2", "bo3") if state.get(f"{name}_results")}
        report = agent._report(state["month"], state["mode"], state.get("kpi_values"), state.get("historical_comparisons"),
                               state.get("detected_anomalies", []), state.get("segment_analysis", {}), insights, [])
        return {"deterministic_report": report}

    def prioritization(state: OM5State):
        actions = agent.prioritize_actions(state.get("detected_anomalies", []), state.get("segment_analysis", {}))
        report = state["deterministic_report"]
        if report is not None:
            report.actions = [Line(x["recommendation"], [x["evidence_id"]]) for x in actions] or report.actions
        return {"priority_scores": actions, "deterministic_report": report}

    def gemini(state: OM5State):
        if generator is None:
            return {"generated_report": None, "fallback_reason": "Gemini désactivé ou clé absente"}
        context = agent.generation_context(state)
        generated, latency = generator.generate(context, state.get("validation_errors") or None)
        return {"generated_report": generated, "llm_provider": generator.provider, "llm_model": generator.model,
                "llm_latency_ms": latency, "generation_mode": "gemini"}

    def validation(state: OM5State):
        generated = state.get("generated_report")
        if not generated:
            return {"validation_status": "unavailable", "validation_errors": state.get("validation_errors", []) or [state.get("fallback_reason") or "sortie absente"]}
        ok, errors = validate_generated_report(generated, agent.log, state["month"], state["mode"],
                                               state.get("kpi_values") or {}, state.get("priority_scores", []),
                                               {x for x in ("bo1", "bo2", "bo3") if state.get(f"{x}_results")})
        return {"validation_status": "valid" if ok else "invalid", "validation_errors": errors,
                "retry_counter": state.get("retry_counter", 0) + (0 if ok else 1)}

    def validation_route(state: OM5State) -> str:
        if state.get("validation_status") == "valid":
            return "final"
        if generator is not None and state.get("generated_report") is not None and state.get("retry_counter", 0) <= 1:
            return "retry"
        return "fallback"

    def fallback(state: OM5State):
        return {"generated_report": None, "generation_mode": "deterministic", "fallback_used": True,
                "fallback_reason": state.get("fallback_reason") or "; ".join(state.get("validation_errors", [])) or "validation impossible"}

    def final(state: OM5State):
        report = state.get("deterministic_report") or Report(title=f"OM5 — Pilotage marketplace {state['month']}")
        generated = state.get("generated_report")
        if generated:
            report.narrative = generated.get("executive_summary", report.narrative)
            report.narrative_source = "gemini"
            report.actions = [Line(x["description"], x.get("evidence_ids", [])) for x in generated.get("recommendations", [])]
        ok, problems = validate_report(report, agent.log)
        metadata = {
            "evidence_valid": ok, "validation_problems": problems, "partial": agent.partial,
            "tool_trace": agent.trace, "call_budget": agent.max_calls, "calls_used": len(agent._seen),
            "anomalies": state.get("detected_anomalies", []), "comparisons": state.get("historical_comparisons"),
            "segments": state.get("segment_analysis", {}),
            "agent_insights": {x: state.get(f"{x}_results") for x in ("bo1", "bo2", "bo3") if state.get(f"{x}_results")},
            "recommendations": state.get("priority_scores", []), "generated_content": generated,
            "contextual_recommendations": (generated or {}).get("recommendations", []),
            "trends": agent.get_trends(state["mode"]),
            "generation_mode": state.get("generation_mode", "deterministic"), "llm_provider": state.get("llm_provider"),
            "llm_model": state.get("llm_model"), "llm_latency_ms": state.get("llm_latency_ms"),
            "validation_status": state.get("validation_status", "not_run"), "validation_errors": state.get("validation_errors", []),
            "fallback_used": state.get("fallback_used", False), "fallback_reason": state.get("fallback_reason"),
            "graph_engine": "langgraph", "graph_retries": state.get("retry_counter", 0),
            "evidence": [asdict(x) for x in agent.log.with_prefix("")],
        }
        report.meta.update(metadata)
        return {"final_report": report, "evidence": metadata["evidence"], "tool_trace": agent.trace, "partial": agent.partial}

    graph = StateGraph(OM5State)
    for name, fn in (("kpi", kpi), ("comparisons", comparisons), ("anomaly_detection", anomalies),
                     ("segment_analysis", segments), ("planner", planner), ("agent_execution", execute),
                     ("consolidation", consolidation), ("prioritization", prioritization),
                     ("gemini_generation", gemini), ("validation", validation),
                     ("deterministic_fallback", fallback), ("final_report", final)):
        graph.add_node(name, _node(agent, name, fn))
    graph.add_edge(START, "kpi"); graph.add_edge("kpi", "comparisons"); graph.add_edge("comparisons", "anomaly_detection")
    graph.add_conditional_edges("anomaly_detection", route, {"segments": "segment_analysis", "consolidation": "consolidation"})
    graph.add_edge("segment_analysis", "planner"); graph.add_edge("planner", "agent_execution"); graph.add_edge("agent_execution", "consolidation")
    graph.add_edge("consolidation", "prioritization"); graph.add_edge("prioritization", "gemini_generation"); graph.add_edge("gemini_generation", "validation")
    graph.add_conditional_edges("validation", validation_route, {"final": "final_report", "retry": "gemini_generation", "fallback": "deterministic_fallback"})
    graph.add_edge("deterministic_fallback", "final_report"); graph.add_edge("final_report", END)
    return graph.compile()


def graph_mermaid(agent: "ReportingAgent", generator: ReportGenerator | None = None) -> str:
    return build_om5_graph(agent, generator).get_graph().draw_mermaid()
