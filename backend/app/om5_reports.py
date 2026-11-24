"""OM5 marketplace exports (kept separate from BO3 seller reports)."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    out = io.StringIO(newline="")
    if not rows:
        return b""
    fields = sorted({key for row in rows for key in row})
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    return out.getvalue().encode("utf-8-sig")


def report_pdf(payload: dict[str, Any]) -> bytes:
    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
                            title=payload["report"]["title"])
    styles = getSampleStyleSheet()
    story = [Paragraph(payload["report"]["title"], styles["Title"]), Spacer(1, 5 * mm)]
    report = payload["report"]
    for title, key in (("Résumé", "narrative"), ("Faits observés", "facts"), ("Estimations", "estimates"),
                       ("Actions recommandées", "actions"), ("Limites", "caveats")):
        story.append(Paragraph(title, styles["Heading2"]))
        value = report.get(key) or []
        if isinstance(value, str):
            story.append(Paragraph(value, styles["BodyText"]))
        else:
            for item in value:
                text = item if isinstance(item, str) else item.get("text", "")
                refs = "" if isinstance(item, str) else " · ".join(item.get("evidence", []))
                story.append(Paragraph(f"• {text}" + (f" <font size='7'>[{refs}]</font>" if refs else ""), styles["BodyText"]))
    trace = report.get("meta", {}).get("tool_trace", [])
    if trace:
        story += [Paragraph("Trace d'exécution", styles["Heading2"])]
        rows = [["Outil", "Statut", "Durée (ms)"]] + [[x.get("tool"), x.get("status"), x.get("duration_ms", "—")] for x in trace]
        table = Table(rows, colWidths=[90 * mm, 35 * mm, 30 * mm])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#132238")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                   ("GRID", (0, 0), (-1, -1), .25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        story.append(table)
    doc.build(story)
    return stream.getvalue()

