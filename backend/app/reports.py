"""Export des audits vendeur : PDF (rapport complet) et CSV (preuves).

Le PDF ne contient que (1) les sorties des outils déterministes de BO3 et (2), en option, la dernière analyse IA DÉJÀ VALIDÉE
pour ce vendeur et ce mois (fichier data/model/llm_analyses/…), dans une section explicitement marquée comme générée par IA.
Aucun appel LLM n'est fait ici ; aucune hypothèse n'est présentée comme confirmée.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import sys
from xml.sax.saxutils import escape

from .config import ROOT

sys.path.insert(0, str(ROOT / "src"))
from agents.category_labels import cat_label  # noqa: E402
from agents.bo3_agent import uf_name  # noqa: E402

METRIC_LABEL = {"late": "Retard de livraison", "poor": "Avis 1-2 étoiles", "handover": "Remise tardive au transporteur"}
_FONT = {"name": None}


def _font() -> tuple[str, str]:
    if _FONT["name"] is None:
        for regular, bold in (("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
                              ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                              ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf")):
            if Path(regular).exists() and Path(bold).exists():
                pdfmetrics.registerFont(TTFont("SI", regular))
                pdfmetrics.registerFont(TTFont("SI-B", bold))
                _FONT["name"] = ("SI", "SI-B")
                break
        else:
            _FONT["name"] = ("Helvetica", "Helvetica-Bold")
    return _FONT["name"]


def _txt(s: object) -> str:
    t = escape(str(s if s is not None else "—"))
    if _font()[0] == "Helvetica":  # police de secours sans Unicode étendu
        t = t.replace("≥", ">=").replace("≤", "<=").replace("→", "->").replace("×", "x").replace("…", "...").replace("–", "-").replace("’", "'")
    return t


def _pct(x) -> str:
    return "—" if x is None else f"{100 * float(x):.1f} %".replace(".", ",")


FR_MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
SHORT_LABEL = {"handover": "Expédition tardive", "late": "Livraison en retard", "poor": "Avis négatifs (1-2 étoiles)"}
EXPLAIN = {"handover": "commandes remises au transporteur après la date limite",
           "late": "commandes livrées après la date annoncée au client",
           "poor": "commandes notées 1 ou 2 étoiles par le client"}
SEV_COLOR = {"élevée": "#8B1E3F", "moyenne": "#8A5A00", "faible": "#475569"}


def _month_fr(m: str | None) -> str:
    try:
        y, mo = str(m).split("-")
        return f"{FR_MONTHS[int(mo) - 1]} {y}"
    except (ValueError, IndexError):
        return str(m or "—")


def _num(x, nd: int = 0) -> str:
    if x is None:
        return "—"
    return f"{float(x):,.{nd}f}".replace(",", " ").replace(".", ",")


def seller_pdf(audit: dict, history_rows: list[dict], ai: dict | None) -> bytes:
    """Bilan vendeur « direction » : en-tête et statut, indicateurs clés (vendeur / marketplace / catégorie / meilleur quart),
    positionnement concurrentiel, analyse stratégique validée (diagnostic croisé, plan de remontée, questions), voix des clients,
    commandes à examiner, historique des alertes, méthode. Uniquement des contenus lisibles : ni identifiant de preuve ni donnée brute."""
    reg, bold = _font()
    INK, MUTED, LINE, TINT = colors.HexColor("#132238"), colors.HexColor("#475569"), colors.HexColor("#E2E8F0"), colors.HexColor("#F8F9FA")
    ACCENT = colors.HexColor("#132238")
    st = {"title": ParagraphStyle("title", fontName=bold, fontSize=19, leading=23, textColor=colors.white),
          "sub": ParagraphStyle("sub", fontName=reg, fontSize=9, leading=12, textColor=colors.HexColor("#F6E08D")),
          "badge": ParagraphStyle("badge", fontName=bold, fontSize=9.5, leading=12, textColor=colors.white, alignment=2),
          "h2": ParagraphStyle("h2", fontName=bold, fontSize=12.5, leading=16, textColor=ACCENT, spaceBefore=12, spaceAfter=5),
          "h3": ParagraphStyle("h3", fontName=bold, fontSize=9.6, leading=12.5, textColor=INK, spaceBefore=6, spaceAfter=3),
          "p": ParagraphStyle("p", fontName=reg, fontSize=9.2, leading=13, textColor=INK, spaceAfter=4),
          "lead": ParagraphStyle("lead", fontName=reg, fontSize=10, leading=14.5, textColor=INK, spaceAfter=6),
          "b": ParagraphStyle("b", fontName=reg, fontSize=9.2, leading=13, textColor=INK, leftIndent=10, bulletIndent=0, spaceAfter=3),
          "s": ParagraphStyle("s", fontName=reg, fontSize=7.8, leading=10.2, textColor=MUTED, spaceAfter=2),
          "c": ParagraphStyle("c", fontName=reg, fontSize=8.4, leading=10.8, textColor=INK),
          "cb": ParagraphStyle("cb", fontName=bold, fontSize=8.4, leading=10.8, textColor=INK),
          "ch": ParagraphStyle("ch", fontName=bold, fontSize=7.8, leading=10, textColor=MUTED),
          "k": ParagraphStyle("k", fontName=reg, fontSize=7.6, leading=9.6, textColor=MUTED),
          "kv": ParagraphStyle("kv", fontName=bold, fontSize=10.5, leading=13, textColor=INK),
          "q": ParagraphStyle("q", fontName=reg, fontSize=8.8, leading=12.4, textColor=INK, leftIndent=8, borderPadding=(4, 6, 4, 6),
                              backColor=colors.HexColor("#F8F9FA"), spaceBefore=2, spaceAfter=6)}
    rep, ev = audit["report"], {e["id"]: e.get("payload") or {} for e in audit["evidence"]}
    meta = rep.get("meta") or {}
    sid, month = meta.get("seller_id", ""), meta.get("month", "")
    s8 = sid[:8]
    prof = ev.get(f"sel:{s8}:{month}") or {}
    bench = ev.get(f"peer:bench:{s8}:{month}") or {}
    voice = ev.get(f"mdl:aspects:seller:{s8}:{month}") or {}
    orders = ev.get(f"ord:seller:{s8}:{month}") or {}
    kpi = {m: ev.get(f"kpi:seller:{s8}:{month}:{m}") or {} for m in SHORT_LABEL}
    det = {m: (ev.get(f"alr:{s8}:{month}:{m}") or {}).get("families") or {} for m in SHORT_LABEL}
    story: list = []

    def P(t: str, k: str = "p") -> None:
        story.append(Paragraph(t, st[k]))

    def B(t: str) -> None:
        story.append(Paragraph(t, st["b"], bulletText="•"))

    def T(rows: list[list], widths: list[float], header: bool = True, styles: list | None = None) -> None:
        data = [[c if isinstance(c, Paragraph) else Paragraph(_txt(c), st["ch"] if header and i == 0 else st["c"]) for c in r] for i, r in enumerate(rows)]
        t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
                               ("BACKGROUND", (0, 0), (-1, 0), TINT if header else colors.white), ("TOPPADDING", (0, 0), (-1, -1), 4),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                               *(styles or [])]))
        story.append(t)
        story.append(Spacer(1, 5))

    # ---- statut global
    alerts = [(m, f) for m in SHORT_LABEL for f, x in det[m].items() if x.get("alert")]
    sevs = [det[m]["level"].get("severity") for m in SHORT_LABEL if (det[m].get("level") or {}).get("alert")]
    top_sev = next((s for s in ("élevée", "moyenne", "faible") if s in sevs), None)
    if top_sev:
        status, scolor = f"Alerte — priorité {top_sev}", SEV_COLOR[top_sev]
    elif alerts:
        status, scolor = "Signal de tendance à surveiller", "#1E3A66"
    else:
        status, scolor = "Aucune alerte", "#1B4332"

    # ---- en-tête
    head = Table([[[Paragraph("Bilan vendeur", st["title"]),
                    Paragraph(f"Vendeur {_txt(s8)} · situation à fin {_txt(_month_fr(month))} · données connues au {_txt(meta.get('decision_date'))}", st["sub"])],
                   Paragraph(_txt(status), st["badge"])]], colWidths=[132 * mm, 50 * mm])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#132238")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                              ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                              ("BACKGROUND", (1, 0), (1, 0), colors.HexColor(scolor))]))
    story += [head, Spacer(1, 6)]
    seg = prof.get("descriptive_segment") or {}
    fl = prof.get("flows") or {}
    cells = [("Catégorie principale", cat_label(prof.get("main_category")) if prof.get("main_category") else "—"), ("État du vendeur", uf_name(prof.get("seller_state")) or "—"),
             ("Commandes sur 12 mois", _num(prof.get("orders_12m"))), ("Profil", " · ".join(x for x in (seg.get("volume"), seg.get("region")) if x) or "—"),
             ("Hors de son État", _pct(fl.get("interstate_share")) if fl.get("interstate_share") is not None else "—")]
    strip = Table([[[Paragraph(_txt(k), st["k"]), Paragraph(_txt(v), st["kv"])] for k, v in cells]], colWidths=[w * mm for w in (50, 26, 32, 42, 32)])
    strip.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, LINE), ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("LEFTPADDING", (0, 0), (-1, -1), 6)]))
    story += [strip, Spacer(1, 4)]

    # ---- synthèse
    P("Synthèse", "h2")
    P(_txt((ai or {}).get("resume") or rep.get("narrative")), "lead")

    # ---- indicateurs clés
    P("Indicateurs clés", "h2")
    cat = (bench.get("category") or {}).get("metrics") or {}
    rows = [["Indicateur", "Vendeur · 3 derniers mois", "Marketplace", "Médiane de la catégorie*", "Meilleur quart*", "Rang dans la catégorie*", "Statut"]]
    sty = []
    for i, m in enumerate(SHORT_LABEL, start=1):
        o, c, lv, tr = kpi[m], cat.get(m) or {}, det[m].get("level") or {}, det[m].get("trend") or {}
        if lv.get("alert"):
            stxt, col = f"Alerte (priorité {lv.get('severity')})", SEV_COLOR.get(lv.get("severity"), "#b91c1c")
        elif tr.get("alert"):
            stxt, col = "Dégradation récente", "#1E3A66"
        elif lv.get("eligible"):
            stxt, col = "Conforme", "#1B4332"
        else:
            stxt, col = "Volume insuffisant", "#6b7280"
        rate = f"{_pct(o.get('recent_rate'))} <font size='7' color='#6b7280'>sur {_num(o.get('recent_known_n'))} commandes</font>" if o.get("recent_known_n") else "—"
        rows.append([Paragraph(f"<b>{_txt(SHORT_LABEL[m])}</b><br/><font size='7' color='#6b7280'>{_txt(EXPLAIN[m])}</font>", st["c"]),
                     Paragraph(rate, st["cb"]), _pct(o.get("peer_rate")), _pct(c.get("group_median")), _pct(c.get("top_quartile_threshold")),
                     f"{c['rank']} sur {c['n_ranked']}" if c.get("rank") else "non classé", Paragraph(f"<font color='{col}'><b>{_txt(stxt)}</b></font>", st["c"])])
    T(rows, [44, 30, 20, 24, 20, 22, 22], styles=sty)
    P("* Sur 12 mois, parmi les vendeurs de la même catégorie principale ; le rang 1 correspond au taux le plus bas (le meilleur). "
      "Meilleur quart : taux à atteindre pour faire partie des 25 % de vendeurs les plus performants de la catégorie.", "s")

    # ---- positionnement concurrentiel
    dc = bench.get("direct_competitors") or {}
    if cat:
        P("Positionnement concurrentiel", "h2")
        for g, title in ((bench.get("category") or {}, "Dans sa catégorie"), (dc, "Face à ses concurrents directs")):
            ov = g.get("overall") or {}
            if not g:
                continue
            parts = [f"{SHORT_LABEL[m].lower()} : rang {x['rank']} sur {x['n_ranked']}" for m in SHORT_LABEL if (x := (g.get("metrics") or {}).get(m) or {}).get("rank")]
            txt = f"<b>{_txt(title)}</b> ({_txt(_num(g.get('n_members')))} vendeurs) — classement général "
            txt += f"{ov['rank']} sur {ov['n_ranked']}" if ov.get("rank") else "non disponible"
            txt += (", dans le meilleur quart" if ov.get("in_top_quartile") else "") + (f" ; {_txt(' ; '.join(parts))}." if parts else ".")
            B(txt)
        prow = [["Profil commercial", "Vendeur", "Médiane catégorie", "Médiane concurrents directs", "Meilleur quart catégorie"]]
        fmt = {"median_price": lambda v: "—" if v is None else f"{_num(v, 2)} R$", "freight_share": _pct,
               "promised_days": lambda v: "—" if v is None else f"{_num(v, 1)} jours"}
        for key, label in (("median_price", "Prix médian"), ("freight_share", "Part des frais de port dans le prix"), ("promised_days", "Délai annoncé au client")):
            x, y = cat.get(key) or {}, ((dc.get("metrics") or {}).get(key)) or {}
            prow.append([label, Paragraph(f"<b>{_txt(fmt[key](x.get('seller_value')))}</b>", st["c"]), fmt[key](x.get("group_median")),
                         fmt[key](y.get("group_median")), fmt[key](x.get("top_quartile_median"))])
        story.append(Spacer(1, 3))
        T(prow, [52, 30, 32, 38, 30])
        comps = (bench.get("competitors") or [])[:5]
        if comps:
            crow = [["Concurrent direct", "Catégorie", "Commandes 12 mois", "Expédition tardive", "Livraison en retard", "Avis négatifs"]]
            for c in comps:
                crow.append([str(c.get("seller_id", ""))[:8], cat_label(c.get("main_category")), _num(c.get("orders_12m")),
                             _pct(c.get("rate_handover")), _pct(c.get("rate_late")), _pct(c.get("rate_poor"))])
            P("Concurrents directs les plus proches (activité, volume, prix, frais de port et délai comparables)", "h3")
            T(crow, [28, 46, 26, 28, 28, 26])

    # ---- analyse stratégique (contenu IA validé)
    P("Analyse stratégique", "h2")
    if ai:
        P("Rédigée par l'assistant à partir des seules données de ce bilan ; chaque chiffre a été contrôlé automatiquement. "
          "Les lectures et les pistes sont des hypothèses à valider avec le vendeur.", "s")
        sec = ai.get("sections") or {}
        for key, title in (("diagnostic", "Diagnostic croisé"), ("positionnement", "Positionnement concurrentiel"),
                           ("hypotheses", "Lectures possibles"), ("points_forts", "Points forts"), ("inconnues", "À confirmer")):
            items = sec.get(key) or (sec.get("comparaison") if key == "positionnement" else None) or []
            if items:
                P(title, "h3")
                for it in items:
                    B(_txt(it.get("texte")))
        if ai.get("actions"):
            P("Plan de remontée", "h3")
            T([["Priorité", "Piste d'amélioration", "Objectif"]] +
              [[Paragraph(f"<b>{_txt((a.get('priorite') or '').capitalize())}</b>", st["c"]), a.get("action"), a.get("cible") or a.get("direction_attendue") or "—"]
               for a in ai["actions"]], [20, 112, 50])
        if ai.get("questions"):
            P("Questions d'investigation", "h3")
            for q in ai["questions"]:
                B(_txt(q.get("texte")))
    else:
        P("L'analyse stratégique n'a pas encore été générée pour ce vendeur et ce mois : utilisez « Générer l'analyse stratégique » "
          "dans l'onglet Bilan de l'application, puis téléchargez à nouveau ce bilan.", "s")
        if rep.get("actions"):
            P("Actions suggérées par l'audit", "h3")
            for ln in rep["actions"]:
                B(_txt(ln.get("text")))

    # ---- voix des clients
    if voice.get("available") and voice.get("n_written_reviews"):
        P("Ce que disent les clients", "h2")
        neg = ", ".join(f"{r['label'].lower()} ({r['negative']} avis)" for r in (voice.get("top_negative") or [])[:4])
        P(f"{_num(voice['n_written_reviews'])} avis écrits sur 12 mois, dont {_pct(voice.get('share_rated_1_2'))} notés 1 ou 2 étoiles. "
          + (f"Sujets les plus critiqués : {_txt(neg)}." if neg else ""))
        for q in (voice.get("quotes") or [])[:3]:
            lang = "traduction automatique" if q.get("machine_translated") else "texte original en portugais"
            story.append(Paragraph(f"« {_txt(q.get('excerpt'))} »<br/><font size='7' color='#6b7280'>Note {q.get('score')}/5 · {_txt(q.get('aspect'))} · {lang}</font>", st["q"]))

    # ---- commandes à examiner
    shown = orders.get("shown") or []
    if shown:
        P("Commandes récentes à examiner", "h2")
        P(f"{_num(orders.get('orders_with_known_problem'))} commandes des trois derniers mois présentaient déjà un problème connu à la date du bilan, "
          f"sur {_num(orders.get('orders_recent'))}.", "s")
        orow = [["Commande", "Date d'achat", "Destination", "Catégorie", "Problème constaté"]]
        for c in shown[:5]:
            det_txt = [p for p in c.get("problems") or []]
            if c.get("handover_delay_days") is not None:
                det_txt.append(f"expédiée {c['handover_delay_days']} j après la limite")
            if c.get("late_days") is not None:
                det_txt.append(f"livrée {c['late_days']} j après la date annoncée")
            if c.get("review_score") is not None:
                det_txt.append(f"note {c['review_score']}/5")
            orow.append([f"#{str(c.get('order_id', ''))[:8]}", c.get("purchase_date"), uf_name(c.get("customer_state")), cat_label(c.get("category")), " ; ".join(det_txt)])
        T(orow, [22, 22, 20, 40, 78])

    # ---- historique des alertes
    P("Historique des alertes", "h2")
    if history_rows:
        T([["Mois", "Indicateur", "Type", "Statut", "Priorité", "Taux du vendeur", "Référence"]] +
          [[_month_fr(r["month"]), SHORT_LABEL.get(r["metric"], r["metric"]), {"level": "écart à la marketplace", "trend": "dégradation récente"}.get(r["family"], r["family"]),
            {"new": "nouvelle", "ongoing": "en cours", "resolved": "résolue"}.get(r["status"], r["status"]), r.get("severity") or "—",
            _pct(r.get("recent_rate")), _pct(r.get("baseline"))] for r in history_rows[:24]],
          [24, 36, 34, 18, 18, 26, 22])
    else:
        P("Aucune alerte enregistrée pour ce vendeur jusqu'à ce mois.", "s")

    # ---- méthode
    P("Méthode et limites", "h2")
    for t in ("Chiffres calculés sur les commandes d'un seul vendeur et uniquement avec les informations connues à la fin du mois du bilan : "
              "les commandes encore en cours de livraison ne sont pas comptées.",
              "Une alerte signale un écart à investiguer par rapport à la marketplace (ou au propre passé du vendeur), pas une faute ; "
              "les commandes partagées entre plusieurs vendeurs ne lui sont pas attribuées.",
              "Les rangs et le meilleur quart situent le vendeur parmi des vendeurs comparables ; ils ne servent pas à déclencher les alertes.",
              "Les données de la plateforme n'enregistrent pas les causes (stock, effectifs, transporteur) : les lectures proposées sont à confirmer avec le vendeur.",
              "Données Olist historiques (2016-2018). Le détail chiffré de chaque élément est disponible dans l'export CSV des preuves."):
        story.append(Paragraph(_txt(t), st["s"], bulletText="•"))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
                            title=f"Bilan vendeur {s8} — {_month_fr(month)}", author="ShopInsight")

    def footer(c, d):
        c.saveState()
        c.setFont(reg, 7)
        c.setFillColor(MUTED)
        c.drawString(14 * mm, 8 * mm, f"ShopInsight · Bilan vendeur {s8} · fin {_month_fr(month)}")
        c.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {d.page}")
        c.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()


def evidence_csv(audit: dict) -> bytes:
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["identifiant", "nature", "source", "contenu_json"])
    for e in audit["evidence"]:
        w.writerow([e["id"], e["kind"], e["source"], json.dumps(e["payload"], ensure_ascii=False)])
    return ("\ufeff" + out.getvalue()).encode("utf-8")
