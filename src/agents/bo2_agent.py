"""Agent BO2 — DS2.3 « Agent voix du client » (Transformer les avis en actions).

Questions traitées : « Que critiquent / apprécient les clients (en [mois], dans [État], pour [catégorie]) ? », « Y a-t-il de nouvelles plaintes ? »,
« Montre-moi des avis sur la livraison à AL. » — avec les actions à confier à chaque équipe.

Outils :
  kpi_context          chiffres du mois (gold/monthly_business_kpis) : commandes, retard, notes
  review_volume        combien d'avis écrits, biais de sélection (les clients qui écrivent sont plus mécontents), part traduite
  aspect_profile       aspects les plus critiqués / loués (baseline lexique + note) et part issue de commandes en retard
  emerging_complaints  aspects dont la part de critiques augmente (test + correction BH) et termes nouveaux
  search_reviews       avis représentatifs (recherche TF-IDF PT+FR) avec leur identifiant
Chaque citation d'avis porte son `review_id` ; les extraits français sont signalés comme traduction automatique.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

from .bo2_nlp import ASPECTS, ReviewIndex, analyse_reviews, baseline_months, emerging_aspects, emerging_terms
from .core import (ESTIMATE, FACT, SIMILAR, DataStore, EvidenceLog, LLMClient, Line, Report, Tool, pct, run_tool_loop,
                   to_native, verify_narrative)

TEAM = {
    "livraison": "Logistique et transporteurs",
    "qualite_produit": "Qualité catalogue / gestion des vendeurs",
    "article_errone_ou_manquant": "Gestion des vendeurs (préparation de commande)",
    "vendeur_service": "Support vendeurs",
    "emballage": "Logistique et vendeurs",
    "conformite_annonce": "Équipe catalogue (fiches produit)",
    "prix_valeur": "Marketing / pricing",
    "retour_remboursement": "Service client",
}
ACTION = {
    "livraison": "Analyser les routes et transporteurs concernés ; informer proactivement les clients dont la commande dépasse la promesse.",
    "qualite_produit": "Identifier les catégories et vendeurs les plus cités et déclencher un contrôle qualité ciblé.",
    "article_errone_ou_manquant": "Rappeler aux vendeurs concernés la vérification de préparation (articles, quantités) avant expédition.",
    "vendeur_service": "Vérifier les délais de réponse des vendeurs cités et leur proposer un gabarit de réponse.",
    "emballage": "Vérifier le conditionnement des produits fragiles auprès des vendeurs concernés.",
    "conformite_annonce": "Revoir les fiches produit (photos, couleurs, tailles, description) des articles cités.",
    "prix_valeur": "Surveiller : peu actionnable à court terme.",
    "retour_remboursement": "Simplifier et suivre les délais de traitement des retours et remboursements.",
}
FR_MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
ASPECT_HINTS = {"livraison": ["livraison", "delai", "retard", "colis", "transport", "recu", "arrive"],
                "qualite_produit": ["qualite", "defaut", "casse", "abime", "fonctionne", "panne"],
                "article_errone_ou_manquant": ["erreur", "manquant", "incomplet", "mauvais article", "mauvais produit"],
                "vendeur_service": ["vendeur", "service", "reponse", "contact", "support"],
                "emballage": ["emballage", "carton", "colis abime"],
                "conformite_annonce": ["annonce", "description", "photo", "couleur", "taille", "contrefacon", "conforme"],
                "prix_valeur": ["prix", "cher", "rapport qualite"],
                "retour_remboursement": ["retour", "rembours", "echange", "annul"]}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


class VoiceOfCustomerAgent:
    def __init__(self, project_dir: str | Path = ".", llm: LLMClient | None = None) -> None:
        self.store = DataStore(project_dir)
        self.llm = llm
        self.log = EvidenceLog()
        self._an: pd.DataFrame | None = None
        self._idx: ReviewIndex | None = None
        self.ctx: dict = {"month": None, "state": None, "category": None}

    # ------------------------------------------------------------------ données
    @property
    def an(self) -> pd.DataFrame:
        if self._an is None:
            self._an = analyse_reviews(self.store.reviews())
        return self._an

    @property
    def index(self) -> ReviewIndex:
        if self._idx is None:
            self._idx = ReviewIndex(self.an)
        return self._idx

    def default_month(self, min_reviews: int = 150) -> str:
        c = self.an.groupby("month").size()
        return sorted(m for m in c.index if c[m] >= min_reviews)[-1]

    def _subset(self, month: str | None, state: str | None, category: str | None) -> pd.DataFrame:
        d = self.an
        if month:
            d = d[d["month"] == month]
        if state:
            d = d[d["state"] == state]
        if category:
            d = d[d["category"] == category]
        return d

    def _tag(self, month, state, category) -> str:
        return ":".join(x or "all" for x in (month, state, category))

    # ------------------------------------------------------------------ outils
    def kpi_context(self, month: str) -> dict:
        m = self.store.monthly
        r = m[m["purchase_month"] == month]
        if r.empty:
            raise KeyError(f"Mois {month} absent des KPI.")
        r = r.iloc[0]
        payload = {"month": month, "orders": int(r["order_count"]), "is_complete_period": bool(r["is_complete_period"]),
                   "late_rate": None if pd.isna(r["late_rate"]) else float(r["late_rate"]),
                   "poor_review_rate": None if pd.isna(r["poor_review_rate"]) else float(r["poor_review_rate"]),
                   "average_review_score": None if pd.isna(r["average_review_score"]) else float(r["average_review_score"]),
                   "written_comment_rate": None if "written_comment_rate" not in r or pd.isna(r["written_comment_rate"]) else float(r["written_comment_rate"])}
        self.log.add(f"kpi:monthly:{month}", FACT, "gold/monthly_business_kpis.csv", payload)
        return to_native(payload)

    def review_volume(self, month: str | None = None, state: str | None = None, category: str | None = None) -> dict:
        d = self._subset(month, state, category)
        base = self.store.monthly
        payload = {"month": month, "state": state, "category": category, "written_reviews": int(len(d)),
                   "share_rated_1_2": float((d["score"] <= 2).mean()) if len(d) else None,
                   "share_rated_1_2_all_reviews": None,
                   "share_machine_translated": float((d["translation_status"] == "traduit").mean()) if len(d) else None,
                   "share_to_check": float((d["translation_status"] == "à vérifier").mean()) if len(d) else None}
        if month:
            r = base[base["purchase_month"] == month]
            if len(r) and pd.notna(r.iloc[0]["poor_review_rate"]):
                payload["share_rated_1_2_all_reviews"] = float(r.iloc[0]["poor_review_rate"])
        self.ctx.update({"month": month, "state": state, "category": category})
        self.log.add(f"kpi:reviews:{self._tag(month, state, category)}", FACT, "silver/reviews_text(.fr).jsonl.gz", payload)
        return to_native(payload)

    def aspect_profile(self, month: str | None = None, state: str | None = None, category: str | None = None) -> dict:
        d = self._subset(month, state, category)
        n = len(d)
        rows = []
        for a, (label, _) in ASPECTS.items():
            col = d[f"a_{a}"]
            neg, pos = int((col == -1).sum()), int((col == 1).sum())
            neg_late = d[(col == -1) & d["is_late"].notna()]
            rows.append({"aspect": a, "label": label, "mentions": int(col.notna().sum()), "negative": neg, "positive": pos,
                         "negative_share_of_reviews": neg / n if n else None, "positive_share_of_reviews": pos / n if n else None,
                         "late_share_among_negative": float((neg_late["is_late"] == 1).mean()) if len(neg_late) >= 10 else None,
                         "n_negative_with_delivery_status": int(len(neg_late))})
        payload = {"month": month, "state": state, "category": category, "n_reviews": int(n), "aspects": rows,
                   "method": "baseline mots-clés (portugais) + polarité de phrase / note ; NON validée (pas d'échantillon annoté)"}
        self.ctx.update({"month": month, "state": state, "category": category})
        self.log.add(f"mdl:aspects:{self._tag(month, state, category)}", ESTIMATE, "bo2_nlp.LexiconAspectModel", payload)
        return to_native(payload)

    def emerging_complaints(self, month: str | None = None) -> dict:
        month = month or self.default_month()
        res = emerging_aspects(self.an, month)
        res["terms"] = emerging_terms(self.an, month, res["baseline_months"]) if res["aspects"] else []
        res["method"] = "médiane des 12 mois précédents + variabilité mensuelle (MAD), test unilatéral, correction BH ; termes : log-odds avec a priori de Dirichlet"
        self.ctx["month"] = month
        self.log.add(f"mdl:emerging:{month}", ESTIMATE, "bo2_nlp.emerging_aspects / emerging_terms", res)
        return to_native(res)

    def search_reviews(self, query: str, month: str | None = None, state: str | None = None, category: str | None = None,
                       sentiment: str | None = None, aspect: str | None = None, k: int = 4) -> dict:
        idx = self.index
        df = idx.df
        mask = np.ones(len(df), dtype=bool)
        if month:
            mask &= (df["month"] == month).values
        if state:
            mask &= (df["state"] == state).values
        if category:
            mask &= (df["category"] == category).values
        if sentiment == "negatif":
            mask &= (df["score"] <= 2).values
        elif sentiment == "positif":
            mask &= (df["score"] >= 4).values
        if aspect in ASPECTS:
            mask &= (df[f"a_{aspect}"] == (1 if sentiment == "positif" else -1)).values
        hits = idx.search(query, mask, k)
        out = []
        for _, r in hits.iterrows():
            fr_ok = bool(r["full_fr"]) and r["translation_status"] == "traduit"
            text = r["full_fr"] if fr_ok else r["full_pt"]
            item = {"review_id": r["review_id"], "order_id": r["order_id"], "score": int(r["score"]), "month": r["month"], "state": r["state"],
                    "category": r["category"], "excerpt": (text[:240] + "…") if len(text) > 240 else text,
                    "machine_translated": fr_ok, "original_pt": (r["full_pt"][:160] + "…") if len(r["full_pt"]) > 160 else r["full_pt"],
                    "similarity": round(r["similarity"], 3)}
            out.append(item)
            self.log.add(f"rev:{r['review_id']}", SIMILAR, "silver/reviews_text(.fr).jsonl.gz (propos d'un client)", item)
        payload = {"query": query, "filters": {"month": month, "state": state, "category": category, "sentiment": sentiment, "aspect": aspect},
                   "results": out}
        self.log.add(f"ctx:search:{abs(hash((query, month, state, category, sentiment, aspect))) % 10**8}", SIMILAR, "TF-IDF PT+FR", {"n": len(out)})
        return to_native(payload)

    # ------------------------------------------------------------------ composition
    def report(self, month: str | None = None, state: str | None = None, category: str | None = None, focus: str | None = None,
               sentiment_focus: str = "negatif", use_llm: bool = True) -> Report:
        """Brief « voix du client » complet pour une période/un segment ; `focus` = aspect à approfondir."""
        self.log = EvidenceLog()
        month = month or self.default_month()
        title = f"Voix du client — {month}" + (f" — État {state}" if state else "") + (f" — {category}" if category else "")
        rep = Report(title)
        try:
            kpi = self.kpi_context(month)
        except KeyError:
            kpi = None
        vol = self.review_volume(month, state, category)
        prof = self.aspect_profile(month, state, category)
        emerg = self.emerging_complaints(month) if not (state or category) else None
        if vol["written_reviews"] < 30:
            rep.facts.append(Line(f"Seulement {vol['written_reviews']} avis écrits pour ce segment : aucune conclusion fiable.", [f"kpi:reviews:{self._tag(month, state, category)}"]))
            rep.caveats.append("Segment trop petit.")
            return rep

        # FAITS
        if kpi:
            rep.facts.append(Line(f"En {month} : {kpi['orders']} commandes, retards {pct(kpi['late_rate'])}, avis 1-2 étoiles {pct(kpi['poor_review_rate'])}, "
                                  f"note moyenne {kpi['average_review_score']:.2f}/5 (toutes commandes).", [f"kpi:monthly:{month}"]))
        v_id = f"kpi:reviews:{self._tag(month, state, category)}"
        txt = f"{vol['written_reviews']} avis écrits dans ce périmètre ; {pct(vol['share_rated_1_2'])} sont notés 1-2"
        if vol["share_rated_1_2_all_reviews"] is not None:
            txt += f", contre {pct(vol['share_rated_1_2_all_reviews'])} pour l'ensemble des avis du mois (les clients qui écrivent sont plus mécontents)"
        rep.facts.append(Line(txt + ".", [v_id]))
        # ESTIMATIONS
        a_id = f"mdl:aspects:{self._tag(month, state, category)}"
        rows = [r for r in prof["aspects"] if r["aspect"] != "satisfaction_globale"]
        crit = sorted(rows, key=lambda r: -r["negative"])[:3]
        praise = sorted(rows, key=lambda r: -r["positive"])[:2]
        for r in crit:
            if r["negative"] == 0:
                continue
            extra = ""
            if r["late_share_among_negative"] is not None:
                extra = f" ; {pct(r['late_share_among_negative'], 0)} de ces critiques viennent de commandes livrées en retard"
            rep.estimates.append(Line(f"Critiqué : « {r['label']} » — {r['negative']} avis ({pct(r['negative_share_of_reviews'])} des avis écrits){extra}.", [a_id]))
        for r in praise:
            if r["positive"] > 0:
                rep.estimates.append(Line(f"Apprécié : « {r['label']} » — {r['positive']} avis positifs ({pct(r['positive_share_of_reviews'])}).", [a_id]))
        alerts = []
        if emerg:
            e_id = f"mdl:emerging:{month}"
            if not emerg["aspects"]:
                rep.estimates.append(Line(f"Détection de plaintes émergentes impossible : {emerg.get('note', 'historique insuffisant')}.", [e_id]))
            else:
                alerts = [a for a in emerg["aspects"] if a["alert"]]
                for a in alerts:
                    rep.estimates.append(Line(f"ALERTE plainte émergente « {a['label']} » : {pct(a['rate'])} des avis écrits de {month} contre {pct(a['baseline_rate'])} "
                                              f"(médiane mensuelle de {emerg['baseline_months'][0]} à {emerg['baseline_months'][-1]}) (×{a['lift']:.1f} ; {a['count']} avis ; z = {a['z']:.1f} ; q = {a['q']:.3f}).", [e_id]))
                if not alerts:
                    rep.estimates.append(Line(f"Aucune plainte émergente détectée en {month} par rapport à la médiane mensuelle de {emerg['baseline_months'][0]} à {emerg['baseline_months'][-1]}.", [e_id]))
                if emerg["terms"]:
                    ts = ", ".join(f"« {t['term']} » ({t['count_month']} ce mois, {t['count_baseline']} sur les {len(emerg['baseline_months'])} mois précédents)" for t in emerg["terms"][:5])
                    rep.estimates.append(Line(f"Termes sur-représentés dans les avis négatifs du mois (portugais) : {ts}.", [e_id]))
                new_terms = [t for t in emerg["terms"] if t["new"] and t["count_month"] >= 15]
                if new_terms:
                    rep.estimates.append(Line("Vocabulaire quasi absent de l'historique (possible nouveau problème, que le lexique d'aspects ne connaît pas) : "
                                              + ", ".join(f"« {t['term']} »" for t in new_terms[:3]) + ".", [e_id]))
        # EXPÉRIENCES D'AUTRES CLIENTS (verbatims)
        asp_for_quotes = [] if sentiment_focus == "positif" else ([focus] if focus in ASPECTS else [r["aspect"] for r in crit[:2] if r["negative"] > 0])
        for a in asp_for_quotes:
            s = self.search_reviews(ASPECTS[a][0], month, state, category, sentiment="negatif", aspect=a, k=2)
            for it in s["results"]:
                mt = " (traduction automatique)" if it["machine_translated"] else " (portugais original)"
                rep.similar.append(Line(f"Client {it['state']}, {it['score']}/5, « {ASPECTS[a][0]} » : « {it['excerpt']} »{mt}", [f"rev:{it['review_id']}"]))
        if emerg and emerg.get("terms"):
            for t in [t for t in emerg["terms"] if t["new"] and t["count_month"] >= 15][:1]:
                s = self.search_reviews(t["term"], month, state, category, sentiment="negatif", k=2)
                for it in s["results"]:
                    mt = " (traduction automatique)" if it["machine_translated"] else " (portugais original)"
                    rep.similar.append(Line(f"Nouveau vocabulaire « {t['term']} » — client {it['state']}, {it['score']}/5 : « {it['excerpt']} »{mt}", [f"rev:{it['review_id']}"]))
                rep.actions.append(Line(f"Relire manuellement les avis contenant « {t['term']} » (nouveau vocabulaire) pour qualifier le problème avant de créer un aspect dédié.", [f"mdl:emerging:{month}"]))
        pr_list = praise if sentiment_focus == "positif" else praise[:1]
        for pr in pr_list:
            if pr["positive"] <= 0:
                continue
            s = self.search_reviews(ASPECTS[pr["aspect"]][0], month, state, category, sentiment="positif", aspect=pr["aspect"], k=2 if sentiment_focus == "positif" else 1)
            for it in s["results"]:
                mt = " (traduction automatique)" if it["machine_translated"] else " (portugais original)"
                rep.similar.append(Line(f"Client satisfait {it['state']}, {it['score']}/5 : « {it['excerpt']} »{mt}", [f"rev:{it['review_id']}"]))
        # ACTIONS
        done = set()
        for a in alerts:
            rep.actions.append(Line(f"PRIORITÉ ({TEAM[a['aspect']]}) — {ACTION[a['aspect']]}", [f"mdl:emerging:{month}"]))
            done.add(a["aspect"])
        for r in crit:
            if r["negative"] and r["aspect"] not in done:
                rep.actions.append(Line(f"({TEAM[r['aspect']]}) — {ACTION[r['aspect']]}", [a_id]))
                done.add(r["aspect"])
        if any(r["aspect"] == "livraison" and (r["late_share_among_negative"] or 0) >= 0.5 for r in rows):
            rep.actions.append(Line("Une majorité des critiques de livraison vient de commandes réellement en retard : coordonner avec l'agent BO1 (commandes à risque) pour intervenir avant la livraison.", [a_id]))
        # LIMITES
        rep.caveats += [
            "Analyse par mots-clés portugais + note (baseline DS2.1) : non évaluée faute d'échantillon annoté ; indicatif, à remplacer par le modèle évalué en F1 par aspect.",
            "Seuls les clients qui écrivent sont représentés (≈ 43 % des avis) et ils sont plus souvent mécontents que l'ensemble.",
            "Les extraits français sont des traductions automatiques ; l'original portugais fait foi. " + (f"{pct(vol['share_to_check'])} des textes de ce périmètre sont marqués « à vérifier »." if vol["share_to_check"] else ""),
            "Associations observées dans des avis historiques (2016–2018), pas de causes.",
        ]
        top = crit[0] if crit and crit[0]["negative"] else None
        new_t = [t["term"] for t in (emerg or {}).get("terms", []) if t["new"] and t["count_month"] >= 15]
        rep.narrative = (f"En {month}, {vol['written_reviews']} avis écrits" + (f" ; critique principale : « {top['label']} » ({top['negative']} avis)" if top else "")
                         + ("" if not (emerg and emerg["aspects"]) else (f" ; alerte sur : {', '.join(a['label'] for a in alerts)}" if alerts else " ; aucune alerte sur les aspects connus"))
                         + (f" ; nouveau vocabulaire repéré : « {new_t[0]} »." if new_t else "."))
        rep.meta = {"month": month, "state": state, "category": category, "alerts": [a["aspect"] for a in alerts]}
        if use_llm and self.llm:
            self._llm_narrative(rep)
        return rep

    # ------------------------------------------------------------------ langage naturel
    def _parse(self, q: str) -> dict:
        f = _fold(q)
        month = None
        m = re.search(r"\b(20\d{2})-(\d{2})\b", f)
        if m:
            month = f"{m.group(1)}-{m.group(2)}"
        else:
            m = re.search(r"\b(" + "|".join(FR_MONTHS) + r")\s+(20\d{2})\b", f)
            if m:
                month = f"{m.group(2)}-{FR_MONTHS[m.group(1)]:02d}"
        states = set(self.an["state"].dropna().unique())
        st = next((t for t in re.findall(r"\b[A-Z]{2}\b", q) if t in states), None)
        cats = self.an["category"].dropna().unique()
        cat = next((c for c in cats if len(c) > 4 and _fold(c.replace("_", " ")) in f), None)
        aspect = None
        for a, hints in ASPECT_HINTS.items():
            if any(h in f for h in hints):
                aspect = a
                break
        intent = "emergent" if re.search(r"nouvell|emergen|alerte|apparu|augment", f) else ("positif" if re.search(r"apprecie|positi|satisfait|aime", f) else "negatif")
        return {"month": month, "state": st, "category": cat, "aspect": aspect, "intent": intent}

    def ask(self, question: str) -> Report:
        p = self._parse(question)
        if self.llm:
            self.log = EvidenceLog()
            sys_p = ("Tu es l'agent voix du client REHEARSE. Appelle les outils pour répondre ; aucun chiffre ni citation hors outils. "
                     "Distingue faits, estimations, avis d'autres clients. Les extraits français sont des traductions automatiques. Réponds en français.")
            txt = run_tool_loop(self.llm, sys_p, question, self._tools(), self.log)
            rep = Report("Réponse de l'agent BO2")
            rep.narrative = txt or ""
            return rep
        if p["intent"] == "emergent":
            return self.report(p["month"], p["state"], p["category"], focus=p["aspect"])
        return self.report(p["month"], p["state"], p["category"], focus=p["aspect"], sentiment_focus=p["intent"])

    def _tools(self) -> list[Tool]:
        flt = {"month": {"type": "string", "description": "AAAA-MM"}, "state": {"type": "string", "description": "code État, ex. SP"},
               "category": {"type": "string"}}
        return [
            Tool("kpi_context", "KPI du mois.", {"type": "object", "properties": {"month": {"type": "string"}}, "required": ["month"]}, self.kpi_context),
            Tool("review_volume", "Volume d'avis écrits et biais.", {"type": "object", "properties": flt}, self.review_volume),
            Tool("aspect_profile", "Aspects critiqués / loués.", {"type": "object", "properties": flt}, self.aspect_profile),
            Tool("emerging_complaints", "Plaintes émergentes du mois.", {"type": "object", "properties": {"month": {"type": "string"}}}, self.emerging_complaints),
            Tool("search_reviews", "Avis représentatifs.", {"type": "object", "properties": {**flt, "query": {"type": "string"},
                 "sentiment": {"type": "string", "enum": ["negatif", "positif"]}, "aspect": {"type": "string", "enum": list(ASPECTS)}, "k": {"type": "integer"}},
                 "required": ["query"]}, self.search_reviews),
        ]

    def _llm_narrative(self, rep: Report) -> None:
        payload = json.dumps(to_native({"facts": [vars(x) for x in rep.facts], "estimates": [vars(x) for x in rep.estimates]}), ensure_ascii=False)[:5000]
        try:
            msg = self.llm.chat([
                {"role": "system", "content": "Tu rédiges en français 3 phrases maximum à partir des seules preuves fournies. Aucun chiffre hors preuves. "
                                              "Dis que l'analyse par aspect est une baseline non validée. Pas de cause affirmée."},
                {"role": "user", "content": "Résume la voix du client.\nPREUVES :\n" + payload}])
            text = (msg.get("content") or "").strip()
        except Exception:
            return
        ok, problems = verify_narrative(text, self.log)
        if ok and text:
            rep.narrative, rep.narrative_source = text, "llm_verifie"
        else:
            rep.meta["llm_narrative_rejected"] = problems
