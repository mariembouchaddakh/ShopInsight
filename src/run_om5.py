"""CLI/replay entry point for OM5.

Examples:
    python src/run_om5.py --month 2018-03 --mode as_of --with-agents
    python src/run_om5.py --months 2018-01,2018-02,2018-03 --output-dir reports/om5
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agents.om5_agent import ReportingAgent  # noqa: E402
from backend.app.om5_reports import csv_bytes, report_pdf  # noqa: E402
from backend.app.serialization import evidence_snapshot  # noqa: E402


def build_agent(project_dir: Path, with_agents: bool):
    from backend.app.config import load_settings
    from backend.app.llm.om5_generator import GeminiOM5Generator
    from backend.app.registry import AgentRegistry
    settings = replace(load_settings(), project_dir=project_dir, warmup=False)
    generator = GeminiOM5Generator(settings.gemini_api_key, settings.gemini_model) if settings.om5_llm_enabled and settings.gemini_api_key else None
    if not with_agents:
        return ReportingAgent(project_dir, report_generator=generator)
    registry = AgentRegistry(settings)
    agent = ReportingAgent(project_dir, collaborator=registry.call_public, report_generator=generator)
    return agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Générer/rejouer les rapports mensuels OM5 sur Olist")
    parser.add_argument("--project-dir", type=Path, default=Path("."))
    parser.add_argument("--month")
    parser.add_argument("--months", help="Liste AAAA-MM séparée par des virgules")
    parser.add_argument("--mode", choices=["as_of", "retrospective"], default="as_of")
    parser.add_argument("--with-agents", action="store_true", help="Appeler BO1/BO2/BO3 uniquement si le plan le demande")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/om5"))
    args = parser.parse_args()
    root = args.project_dir.resolve()
    agent = build_agent(root, args.with_agents)
    months = [x.strip() for x in args.months.split(",")] if args.months else [args.month or agent.default_month()]
    out = root / args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for month in months:
        report = agent.run(month, args.mode, args.with_agents)
        payload = {"agent": "om5", "report": report.to_dict(), "markdown": report.to_markdown(), "evidence": evidence_snapshot(agent.log)}
        stem = out / f"om5-{month}-{args.mode}"
        stem.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        stem.with_suffix(".md").write_text(report.to_markdown(), encoding="utf-8")
        stem.with_suffix(".pdf").write_bytes(report_pdf(payload))
        kpis = agent.get_monthly_kpis(month, args.mode)["kpis"]
        Path(f"{stem}-kpis.csv").write_bytes(csv_bytes(kpis))
        Path(f"{stem}-evidence.csv").write_bytes(csv_bytes(evidence_snapshot(agent.log)))
        summary.append({"month": month, "partial": report.meta["partial"], "evidence_valid": report.meta["evidence_valid"],
                        "anomalies": sum(x["anomaly"] for x in report.meta["anomalies"]), "calls": report.meta["calls_used"]})
    print(json.dumps({"output_dir": str(out), "reports": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

