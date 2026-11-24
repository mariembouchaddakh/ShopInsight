"""Evidence checks stricter than the generic number-presence validator."""
from __future__ import annotations

import re
from typing import Iterable

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

