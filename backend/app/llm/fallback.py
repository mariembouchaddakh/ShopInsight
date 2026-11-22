"""Réponses SANS IA de l'assistant (quota gratuit épuisé, clé absente, modèles indisponibles).

L'assistant ne doit jamais laisser l'utilisateur sans réponse : pour les questions fréquentes, la réponse est composée de façon
déterministe à partir des MÊMES preuves que celles données au modèle (aucune interprétation, aucune hypothèse), puis passée au même
validateur que les réponses du modèle. Le mode est signalé à l'interface (« réponse automatique »).
"""
from __future__ import annotations

import re
import unicodedata

import sys

from ..config import ROOT
from .validator import check_item, evidence_log

sys.path.insert(0, str(ROOT / "src"))
from agents.category_labels import cat_label  # noqa: E402

LABEL = {"handover": "expédition tardive (remise au transporteur après la date limite)", "late": "livraison en retard", "poor": "avis négatifs (1 ou 2 étoiles)"}


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def _pct(x) -> str:
    return "n/d" if x is None else f"{100 * float(x):.1f} %".replace(".", ",")


def _find(evidence: list[dict], prefix: str) -> tuple[str, dict] | tuple[None, None]:
    for e in evidence:
        if e["id"].startswith(prefix) and isinstance(e.get("payload"), dict):
            return e["id"], e["payload"]
    return None, None


def _metric(q: str) -> str | None:
    if re.search(r"remise|expedi|transporteur|preparation", q):
        return "handover"
    if re.search(r"avis|note|etoile|satisf", q):
        return "poor"
    if re.search(r"retard|livraison|delai", q):
        return "late"
    return None


# ------------------------------------------------------------------------------------------------ vendeur
def _seller_items(q: str, ev: list[dict]) -> list[dict]:
    out: list[dict] = []
    if re.search(r"avis|client|disent|plain|critiqu", q):
        vid, v = _find(ev, "mdl:aspects:seller:")
        if v and v.get("available") and v.get("n_written_reviews"):
            out.append({"texte": f"Sur les 12 derniers mois, {v['n_written_reviews']} clients ont laissé un avis écrit, dont {_pct(v.get('share_rated_1_2'))} "
                                 "avec une note de 1 ou 2 étoiles.", "type": "fait", "preuves": [vid]})
            neg = v.get("top_negative") or []
            if neg:
                out.append({"texte": "Sujets les plus critiqués : " + ", ".join(f"« {r['label']} » ({r['negative']} avis)" for r in neg[:3]) + ".",
                            "type": "fait", "preuves": [vid]})
            for qt in (v.get("quotes") or [])[:2]:
                rid = f"rev:{qt['review_id']}"
                lang = "traduction automatique" if qt.get("machine_translated") else "texte original en portugais"
                out.append({"texte": f"Un client ({qt['score']}/5, « {qt['aspect']} ») écrit : « {qt['excerpt']} » ({lang}).", "type": "fait", "preuves": [rid]})
        return out
    if re.search(r"concurren|rival|rattrap|meilleur|classement|rang|compar|categorie", q):
        bid, b = _find(ev, "peer:bench:")
        if b and b.get("category"):
            c = b["category"]
            for m in ("handover", "late", "poor"):
                x = (c.get("metrics") or {}).get(m) or {}
                if x.get("rank"):
                    out.append({"texte": f"{LABEL[m].capitalize()} : rang {x['rank']} sur {x['n_ranked']} dans sa catégorie, avec {_pct(x['seller_rate'])} sur "
                                         f"12 mois ; la médiane de la catégorie est de {_pct(x['group_median'])} et le meilleur quart fait "
                                         f"{_pct(x['top_quartile_threshold'])} ou moins.", "type": "fait", "preuves": [bid]})
            comps = (b.get("competitors") or [])[:3]
            if comps:
                out.append({"texte": "Concurrents directs les plus proches : " + " ; ".join(
                    f"{x['seller_id'][:8]} ({cat_label(x['main_category'])}, {x['orders_12m']} commandes sur 12 mois)" for x in comps) + ".", "type": "fait", "preuves": [bid]})
        return out
    # « pourquoi baisse-t-il ? » — alertes actives, puis évolution (uniquement si la question porte là-dessus)
    if not re.search(r"pourquoi|baiss|degrad|alerte|probleme|retard|remise|expedi|evolution|situation|resume|bilan", q):
        return out
    for e in ev:
        if re.match(r"alr:[0-9a-f]{8}:", e["id"]) and isinstance(e.get("payload"), dict):
            p = e["payload"]
            for fam, x in (p.get("families") or {}).items():
                if x.get("alert"):
                    kind = "par rapport à la marketplace" if fam == "level" else "par rapport à son propre passé"
                    out.append({"texte": f"Alerte {kind} sur la {LABEL.get(p['metric'], p['metric'])} : {_pct(x['recent_rate'])} sur les 90 derniers jours "
                                         f"contre {_pct(x['baseline'])} pour la référence.", "type": "fait", "preuves": [e["id"]]})
    hid, h = _find(ev, "kpi:history:")
    if h and h.get("series"):
        for m, ser in h["series"].items():
            pts = [x for x in ser if x.get("known_n") and x.get("rate_90d") is not None]
            if len(pts) >= 2 and any(x.get("alert_level") or x.get("alert_trend") for x in pts):
                out.append({"texte": f"Évolution de la {LABEL.get(m, m)} : {_pct(pts[0]['rate_90d'])} en {pts[0]['month']}, puis "
                                     f"{_pct(pts[-1]['rate_90d'])} en {pts[-1]['month']} (taux sur 90 jours).", "type": "fait", "preuves": [hid]})
    if not out:
        out.append({"texte": "Aucune alerte active pour ce vendeur ce mois-ci.", "type": "fait", "preuves": [e["id"] for e in ev if e["id"].startswith("alr:")][:3]})
    return out


# ------------------------------------------------------------------------------------------------ explication des indicateurs
EXPLAIN = re.compile(r"represent|signifi|veut dire|c.est quoi|ca veut|\bn\s*=|\bn\b|\bvs\b|pourcentage|reference|severite|priorite elevee|niveau|tendance|"
                     r"comment lire|definition|explique|compren|que veut")
METHOD_ID = "ctx:methode"
METHOD_EVIDENCE = {"id": METHOD_ID, "kind": "fait", "source": "définitions de la méthode BO3",
                   "payload": {"fenetre_recente_jours": 90, "historique_mois": 12, "verite_future_jours": 60}}


def _explain_items() -> list[dict]:
    """Définitions (aucun chiffre de vendeur) : ce que signifient les pourcentages, « n », la référence et la priorité."""
    t = [
        "Dans une ligne comme « X % vs Y % (n = N) », X % est la part des commandes du vendeur concernées par le problème (livraison en retard, "
        "avis 1 ou 2 étoiles, ou remise tardive au transporteur) sur ses achats des 90 derniers jours.",
        "N (le « n ») est le nombre de commandes du vendeur sur lesquelles ce pourcentage est calculé : seules comptent celles dont l'issue était déjà "
        "connue à la fin du mois. Plus N est petit, plus le pourcentage est fragile.",
        "Y % est la référence de comparaison : pour une alerte « écart à la marketplace » (niveau), le taux de l'ensemble des vendeurs sur 12 mois ; pour une "
        "alerte « dégradation récente » (tendance), le propre passé du vendeur, c'est-à-dire ses commandes d'il y a 3 à 12 mois.",
        "La priorité d'une alerte : élevée si l'écart est très net et déjà présent le mois précédent ; moyenne si l'écart est net ou déjà signalé ; faible sinon.",
    ]
    return [{"texte": x, "type": "fait", "preuves": [METHOD_ID]} for x in t]


def _cannot(scope: str) -> dict:
    sujets = ("pourquoi ce vendeur baisse, ce que disent ses avis clients, comment il se situe face à ses concurrents, ou ce que signifient les indicateurs"
              if scope == "seller" else
              "quels vendeurs traiter en priorité, quelles catégories ont le plus de retards ou de vendeurs en alerte, ou ce que signifient les indicateurs")
    return {"texte": "Sans l'assistant rédactionnel (quota quotidien de l'IA atteint), je ne peux pas répondre précisément à cette question. "
                     f"Je peux en revanche vous dire {sujets}.", "type": "inconnu", "preuves": []}


# ------------------------------------------------------------------------------------------------ marketplace
def _market_items(q: str, ev: list[dict]) -> list[dict]:
    out: list[dict] = []
    cid, c = _find(ev, "kpi:categories:")
    if c and re.search(r"categor", q):
        if re.search(r"alerte", q):
            rows = c.get("categories_with_most_alerted_sellers") or []
            if rows:
                out.append({"texte": "Catégories qui comptent le plus de vendeurs en alerte : " + " ; ".join(
                    f"{cat_label(r['category'])} ({r['sellers_alerted']} sur {r['sellers_evaluated']} vendeurs)" for r in rows[:5]) + ".", "type": "fait", "preuves": [cid]})
            return out
        m = _metric(q) or "late"
        rows = (c.get("highest_rate_categories") or {}).get(m) or []
        mk = (c.get("marketplace_90d") or {}).get(m) or {}
        if rows:
            out.append({"texte": f"Catégories au taux de {LABEL[m]} le plus élevé sur les 90 derniers jours : " + " ; ".join(
                f"{cat_label(r['category'])} {_pct(r['rate_90d'])} ({r['known_n']} commandes)" for r in rows[:5])
                + f". Moyenne de la marketplace : {_pct(mk.get('rate_90d'))}.", "type": "fait", "preuves": [cid]})
        return out
    lid, al = _find(ev, "alr:list:")
    if al and re.search(r"urgen|priorit|alerte|vendeur|action|traiter|appeler|qui ", q):
        out.append({"texte": f"{al['n_alerted_sellers']} vendeurs sont en alerte ce mois-ci ({al['n_alerts']} alertes).", "type": "fait", "preuves": [lid]})
        for r in (al.get("listing") or [])[:5]:
            det = " ; ".join(f"{LABEL.get(a['metric'], a['metric']).split(' (')[0]} {_pct(a['recent_rate'])} de ses commandes récentes contre {_pct(a['baseline'])} "
                             + ("pour la marketplace" if a.get("family") == "level" else "dans son propre passé") for a in r["alerts"])
            sev = f"priorité {r['top_severity']}" if r.get("top_severity") else "dégradation récente"
            out.append({"texte": f"Vendeur {r['seller_id'][:8]} ({cat_label(r['main_category'])}, {sev}) : {det}.", "type": "fait", "preuves": [lid]})
    return out


def answer_without_llm(question: str, evidence: list[dict], scope: str) -> dict:
    """Réponse factuelle composée à partir des preuves ; chaque élément passe le validateur, sinon il est retiré."""
    q = _fold(question)
    if EXPLAIN.search(q):
        items, evidence = _explain_items(), [*evidence, METHOD_EVIDENCE]
    else:
        items = _seller_items(q, evidence) if scope == "seller" else _market_items(q, evidence)
    log = evidence_log(evidence)
    kept = [it for it in items if (it["preuves"] or it["type"] == "inconnu") and check_item(it["texte"], it["type"], it["preuves"], log).ok]
    if not kept:  # question hors du périmètre des réponses automatiques : on le dit, au lieu de répéter une liste sans rapport
        kept = [_cannot(scope)]
    follow = (["Que disent les avis clients ?", "Comment rattraper ses concurrents ?", "Pourquoi ce vendeur baisse-t-il ?", "Que signifient les pourcentages et le n ?"]
              if scope == "seller" else
              ["Quels vendeurs nécessitent une action urgente ce mois-ci ?", "Quelles catégories ont le plus de retards ?",
               "Quelles catégories concentrent le plus de vendeurs en alerte ?", "Que signifient les pourcentages et le n ?"])
    cited = {c for it in kept for c in it["preuves"]}
    return {"model": None, "mode": "sans_ia", "items": kept, "questions": [], "rejected": [], "follow_up": [f for f in follow if _fold(f) != q][:3],
            "schema_ok": True, "stats": {"rejected_first_pass": 0, "rejected": 0}, "evidence": [e for e in evidence if e["id"] in cited],
            "notice": "Réponse automatique tirée directement des données : le quota quotidien gratuit de l'assistant rédactionnel est atteint "
                      "(il revient demain). Faits et définitions uniquement, sans interprétation."}
