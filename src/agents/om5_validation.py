"""Evidence checks stricter than the generic number-presence validator."""
from __future__ import annotations

import re
from typing import Any, Iterable

from .core import EvidenceLog, Line, Report, verify_narrative


CAUSAL = re.compile(r"\b(cause|causé|provoque|entraîne|responsable de)\b", re.IGNORECASE)


def validate_report(report: Report, log: EvidenceLog) -> tuple[bool, list[str]]:
    problems: list[str] = []
    lines: Iterable[Line] = report.facts + report.estimates + report.similar + report.actions
    for line in lines:
        if not line.evidence:
            problems.append(f"affirmation sans preuve : {line.text[:80]}")
        for ref in line.evidence:
            if log.get(ref) is None:
                problems.append(f"preuve inconnue : {ref}")
        if CAUSAL.search(line.text) and not re.search(r"ne (permet|prouve)|hypothèse|association", line.text, re.I):
            problems.append(f"causalité non démontrée : {line.text[:80]}")
        # A number must occur in the evidence cited by this exact line, not merely
        # somewhere else in the global log. Recommendations are qualitative.
        if line in report.facts + report.estimates + report.similar and line.evidence:
            cited = EvidenceLog()
            for ref in line.evidence:
                ev = log.get(ref)
                if ev is not None:
                    cited.add(ev.id, ev.kind, ev.source, ev.payload)
            ok, line_problems = verify_narrative(line.text, cited)
            if not ok:
                problems.extend(f"{line.text[:35]}… : {p}" for p in line_problems)
    if report.narrative:
        ok, narrative_problems = verify_narrative(report.narrative, log)
        if not ok:
            problems.extend(narrative_problems)
    for ev in log.with_prefix("om5:kpi:"):
        p = ev.payload
        required = {"metric_id", "value", "unit", "period", "source", "mode", "quality_status"}
        missing = sorted(required - set(p))
        if missing:
            problems.append(f"preuve KPI {ev.id} incomplète : {', '.join(missing)}")
        if ev.id != p.get("evidence_id"):
            problems.append(f"identifiant KPI incohérent : {ev.id}")
        if p.get("denominator") == 0 and p.get("value") is not None:
            problems.append(f"division par zéro dans {ev.id}")
    return not problems, problems


def validate_generated_report(payload: dict[str, Any], log: EvidenceLog, month: str, mode: str,
                              kpis: dict[str, Any], priorities: list[dict[str, Any]],
                              available_agents: set[str]) -> tuple[bool, list[str]]:
    """Reject unsupported LLM claims before generated text reaches users."""
    problems: list[str] = []
    if payload.get("period") != month:
        problems.append(f"période incohérente: {payload.get('period')} != {month}")
    if payload.get("temporal_mode") != mode:
        problems.append(f"mode temporel incohérent: {payload.get('temporal_mode')} != {mode}")
    known = {ev.id for ev in log.with_prefix("")}
    allowed_scores = {x["metric_id"]: x["priority_score"] for x in priorities}
    claims: list[dict[str, Any]] = []
    sections = payload.get("sections", {})
    for value in sections.values() if isinstance(sections, dict) else []:
        if isinstance(value, list):
            claims.extend(x for x in value if isinstance(x, dict))
    claims.extend(x for x in payload.get("insights", []) if isinstance(x, dict))
    summary = payload.get("executive_summary", "")
    if isinstance(summary, dict):
        claims.append(summary)
        summary_refs = summary.get("evidence_ids", [])
        if not 2 <= len(summary_refs) <= 5:
            problems.append("la synthèse exécutive doit citer entre deux et cinq preuves")
    else:
        claims.append({"text": summary, "evidence_ids": payload.get("executive_summary_evidence_ids", [])})
    unsupported_causal = re.compile(r"\b(cause|causé|provoque|entraîne|responsable de|prouve que)\b", re.I)
    has_number = re.compile(r"(?<![\w:])[-+]?\d+(?:[.,]\d+)?\s*%?")
    for idx, item in enumerate(claims):
        text = str(item.get("text", ""))
        refs = item.get("evidence_ids", [])
        if text and not refs:
            problems.append(f"affirmation générée sans preuve ({idx})")
        for ref in refs:
            if ref not in known:
                problems.append(f"preuve générée inconnue: {ref}")
        if unsupported_causal.search(text) and not re.search(r"ne (permet|prouve)|hypothèse|association", text, re.I):
            problems.append(f"assertion causale non étayée: {text[:80]}")
        if refs and has_number.search(text):
            cited = EvidenceLog()
            for ref in refs:
                ev = log.get(ref)
                if ev:
                    cited.add(ev.id, ev.kind, ev.source, ev.payload)
            cleaned = text.replace(month, "")
            cleaned = cleaned.replace(month[:4], "")
            for evidence_id in known:
                cleaned = cleaned.replace(evidence_id, "")
            cleaned = re.sub(r"(?:om5:)?(?:kpi|anomaly|comparison|segments|sellers):[\w:.-]+", "", cleaned)
            cleaned = re.sub(r"(?<=\d)[\s\u00a0\u202f](?=\d{3}(?:\D|$))", "", cleaned)
            ok, errors = verify_narrative(cleaned, cited)
            if not ok:
                problems.extend(f"incohérence numérique: {x}" for x in errors)
    recommendation_metrics: list[str] = []
    expected_recommendation_refs = {x["metric_id"]: x.get("evidence_id") for x in priorities}
    collaborator_prefixes = tuple(f"om5:{name}:result:" for name in available_agents)
    for rec in payload.get("recommendations", []):
        refs = rec.get("evidence_ids", [])
        if not refs or any(x not in known for x in refs):
            problems.append(f"référence invalide dans recommandation: {rec.get('title', '?')}")
        metric = rec.get("related_anomaly")
        recommendation_metrics.append(metric)
        if not allowed_scores and metric == "none" and rec.get("priority_score") == 0:
            pass
        elif metric not in allowed_scores:
            problems.append(f"anomalie inconnue dans recommandation: {metric}")
        elif rec.get("priority_score") != allowed_scores[metric]:
            problems.append(f"score modifié par le LLM pour {metric}")
        elif expected_recommendation_refs.get(metric) not in refs:
            problems.append(f"preuve de priorité absente pour {metric}")
        if collaborator_prefixes and not any(str(ref).startswith(collaborator_prefixes) for ref in refs):
            problems.append(f"preuve collaborateur absente pour {metric}")
    insights = payload.get("insights", [])
    sections_seen = [x.get("section") for x in insights if isinstance(x, dict)]
    if len(insights) > 7 or len(sections_seen) != len(set(sections_seen)):
        problems.append("les insights doivent être limités à sept et uniques par section")
    if available_agents and "agents" not in sections_seen:
        problems.append("l'insight agents est requis lorsque des collaborateurs ont été exécutés")
    expected_metrics = set(allowed_scores) or {"none"}
    if set(recommendation_metrics) != expected_metrics or len(recommendation_metrics) != len(expected_metrics):
        problems.append(f"couverture des recommandations incohérente: {recommendation_metrics} != {sorted(expected_metrics)}")
    text_blob = str(payload).lower()
    for name in {"bo1", "bo2", "bo3"} - available_agents:
        if re.search(rf"\b{name}\b.*(?:a conclu|confirme|montre|indique)", text_blob):
            problems.append(f"résultat inventé pour collaborateur indisponible: {name}")
    return not problems, problems

