"""Professional OM5 PDF and CSV exports, rendered only from computed data."""
from __future__ import annotations

import csv
import io
import json
from typing import Any

from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    out = io.StringIO(newline="")
    if not rows:
        return b""
    fields = sorted({key for row in rows for key in row})
    writer = csv.DictWriter(out, fieldnames=fields); writer.writeheader()
    for row in rows:
        writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    return out.getvalue().encode("utf-8-sig")


def report_pdf(payload: dict[str, Any]) -> bytes:
    stream = io.BytesIO(); report = payload["report"]; meta = report.get("meta", {})
    doc = SimpleDocTemplate(stream, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=18*mm,
                            bottomMargin=17*mm, title=report["title"])
    styles = getSampleStyleSheet(); navy, gold, pale, red = (colors.HexColor(x) for x in ("#132238", "#F4D35E", "#F6F7F9", "#9F2842"))
    styles.add(ParagraphStyle(name="Cover", parent=styles["Title"], fontSize=27, leading=32, textColor=navy, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontSize=15, leading=19, textColor=navy, spaceBefore=5*mm, spaceAfter=3*mm))
    styles.add(ParagraphStyle(name="BI", parent=styles["BodyText"], fontSize=9.5, leading=14, textColor=colors.HexColor("#243247"), spaceAfter=2*mm))
    styles.add(ParagraphStyle(name="Small", parent=styles["BodyText"], fontSize=7.5, leading=10, textColor=colors.HexColor("#536174")))
    evidence = meta.get("evidence", []); kpis = [x.get("payload", {}) for x in evidence if str(x.get("id", "")).startswith("om5:kpi:")]
    period = kpis[0].get("period", "—") if kpis else "—"; mode = kpis[0].get("mode", "—") if kpis else "—"
    generation = (f"{str(meta.get('llm_provider')).upper()} · {meta.get('llm_model')} · sortie validée"
                  if meta.get("generation_mode") != "deterministic" else "Repli déterministe")
    story = [Spacer(1, 30*mm), Paragraph("SHOPINSIGHT", styles["Cover"]), Spacer(1, 7*mm),
             Paragraph("RAPPORT DE PILOTAGE MARKETPLACE", ParagraphStyle("Sub", parent=styles["Heading1"], alignment=TA_CENTER, textColor=navy)),
             Spacer(1, 15*mm), _table([["Période", period], ["Mode temporel", mode], ["Génération", generation], ["Périmètre", "Olist · historique 2016–2018"]], [42*mm, 105*mm], navy, pale, first_col=True),
             Spacer(1, 25*mm), Paragraph("Les alertes soutiennent l'investigation humaine et ne déclenchent aucune sanction automatique.", ParagraphStyle("Note", parent=styles["Small"], alignment=TA_CENTER)), PageBreak(),
             Paragraph("Synthèse exécutive", styles["Section"]), Paragraph(report.get("narrative") or "Rapport déterministe.", styles["BI"])]
    if kpis:
        cards = []
        for k in kpis[:8]:
            value = k.get("value"); shown = "—" if value is None else (f"{100*value:.1f} %" if k.get("unit") == "ratio" else f"{value:,.1f} {k.get('unit','')}")
            cards.append(Paragraph(f"<b>{k.get('label','')}</b><br/><font size='13'>{shown}</font><br/><font size='7'>qualité: {k.get('quality_status','')}</font>", styles["BI"]))
        rows = [cards[i:i+4] + [""]*(4-len(cards[i:i+4])) for i in range(0, len(cards), 4)]
        story += [Paragraph("Indicateurs clés", styles["Section"]), _table(rows, [43*mm]*4, navy, pale)]
    usable = [x for x in meta.get("trends", []) if x.get("late_rate") is not None and x.get("poor_review_rate") is not None][-18:]
    if usable:
        chart = HorizontalLineChart(); chart.x=35; chart.y=28; chart.height=72; chart.width=440
        chart.data = [[100*x[m] for x in usable] for m in ("late_rate", "poor_review_rate")]
        chart.categoryAxis.categoryNames = [x["purchase_month"] for x in usable]; chart.categoryAxis.labels.angle=45; chart.categoryAxis.labels.fontSize=6
        chart.valueAxis.valueMin=0; chart.lines[0].strokeColor=red; chart.lines[1].strokeColor=gold; chart.lines[0].strokeWidth=2; chart.lines[1].strokeWidth=2
        drawing=Drawing(500,125); drawing.add(chart); story += [Paragraph("Tendances historiques (%)", styles["Section"]), drawing]
    anomalies = [x for x in meta.get("anomalies", []) if x.get("anomaly")]
    story.append(Paragraph("Anomalies statistiques", styles["Section"]))
    if anomalies:
        rows=[["KPI","Sévérité","Méthode","Valeur","q / z","n"]]+[[x.get("label"),x.get("severity"),x.get("method"),_short_number(x.get("value")),_short_number(x.get("q_value") if x.get("q_value") is not None else x.get("robust_z")),x.get("sample_size")] for x in anomalies]
        story.append(_table(rows,[42*mm,19*mm,39*mm,22*mm,27*mm,18*mm],navy,pale,header=True))
    else:
        story.append(Paragraph("Aucune dégradation statistiquement signalée pour cette période.", styles["BI"]))
    generated=meta.get("generated_content") or {}; sections=generated.get("sections", {})
    insight_groups: dict[str, list[dict[str, Any]]] = {}
    for item in generated.get("insights", []):
        insight_groups.setdefault(item.get("section", "health"), []).append(item)
    generated_sections = [
        ("Santé marketplace et interprétation des KPI", insight_groups.get("health", []) + insight_groups.get("kpi", [])),
        ("Comparaisons et interprétation statistique", insight_groups.get("comparison", []) + insight_groups.get("anomaly", []) + insight_groups.get("statistics", [])),
        ("Analyse géographique et catégories", insight_groups.get("segments", []) or sections.get("geographic_and_category_insights", [])),
        ("Investigations BO1 · BO2 · BO3", insight_groups.get("agents", []) or sections.get("multi_agent_findings", [])),
        ("Impact métier", insight_groups.get("impact", []) or sections.get("business_impact", [])),
        ("Limites de l'analyse", insight_groups.get("limitations", []) or sections.get("data_quality_and_limitations", [])),
    ]
    for title, items in generated_sections:
        if items:
            story.append(Paragraph(title,styles["Section"])); story.extend(Paragraph("• "+x.get("text",""),styles["BI"]) for x in items)
    recs=meta.get("contextual_recommendations") or meta.get("recommendations",[]); story.append(Paragraph("Recommandations prioritaires",styles["Section"]))
    if recs:
        rows=[["Score","Action","Responsable","Échéance","Preuves"]]
        for x in recs:
            refs=x.get("evidence_ids",[x.get("evidence_id","")])
            title=x.get("title") or x.get("recommendation",""); detail=x.get("description","")
            action=f"<b>{title}</b>" + (f"<br/>{detail}" if detail else "")
            rows.append([x.get("priority_score","—"),Paragraph(action,styles["Small"]),x.get("responsible_team","Équipe métier"),x.get("timeframe","À définir"),Paragraph(" · ".join(refs),styles["Small"])])
        story.append(_table(rows,[18*mm,57*mm,31*mm,27*mm,38*mm],navy,pale,header=True))
    story.append(Paragraph("Qualité, limites et méthodologie",styles["Section"])); story.extend(Paragraph("• "+x,styles["BI"]) for x in report.get("caveats",[]))
    story.append(Paragraph("Références de preuve",styles["Section"])); story.extend(Paragraph(f"<b>{x.get('id','')}</b> — {x.get('source','')}",styles["Small"]) for x in evidence)
    trace=meta.get("tool_trace",[])
    if trace:
        rows=[["Nœud / outil","Type","Statut","Durée (ms)"]]+[[x.get("tool"),x.get("kind","tool"),x.get("status"),x.get("duration_ms","—")] for x in trace]
        story += [Paragraph("Trace LangGraph",styles["Section"]),_table(rows,[82*mm,25*mm,30*mm,30*mm],navy,pale,header=True)]
    def footer(canvas, document):
        canvas.saveState(); canvas.setStrokeColor(gold); canvas.line(16*mm,12*mm,194*mm,12*mm); canvas.setFont("Helvetica",7); canvas.setFillColor(navy)
        canvas.drawString(16*mm,8*mm,"ShopInsight · OM5 · données historiques Olist"); canvas.drawRightString(194*mm,8*mm,f"Page {document.page}"); canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer); return stream.getvalue()


def _table(rows: list[list[Any]], widths: list[float], navy, pale, header: bool=False, first_col: bool=False) -> Table:
    table=Table(rows,colWidths=widths,repeatRows=1 if header else 0)
    rules=[("GRID",(0,0),(-1,-1),.25,colors.HexColor("#B8C1CE")),("VALIGN",(0,0),(-1,-1),"TOP"),("FONTSIZE",(0,0),(-1,-1),7.5),("PADDING",(0,0),(-1,-1),5)]
    if header: rules += [("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,pale])]
    elif first_col: rules += [("BACKGROUND",(0,0),(0,-1),navy),("TEXTCOLOR",(0,0),(0,-1),colors.white),("BACKGROUND",(1,0),(1,-1),pale),("FONTNAME",(0,0),(0,-1),"Helvetica-Bold")]
    else: rules += [("BACKGROUND",(0,0),(-1,-1),pale),("INNERGRID",(0,0),(-1,-1),2,colors.white)]
    table.setStyle(TableStyle(rules)); return table


def _short_number(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)
