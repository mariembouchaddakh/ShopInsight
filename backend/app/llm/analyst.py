"""Analyste vendeur (LLM) : interprète les preuves déterministes de BO3, sans jamais calculer ni décider.

Flux : audit BO3 (outils déterministes, y compris voix des clients BO2 et commandes concrètes) → paquet de preuves nettoyé
→ LLM (JSON imposé) → validation élément par élément → une passe de correction pour les éléments rejetés → seul le contenu validé est rendu.
Le LLM ne crée ni ne supprime d'alerte, ne calcule aucun taux et ne change aucune décision ; s'il est indisponible, l'audit déterministe reste complet.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .provider import LLMError, LLMProvider
from .validator import HEDGE, check_item, evidence_log

ITEM_SECTIONS = ("situation", "diagnostic", "positionnement", "faiblesses", "points_forts", "hypotheses", "inconnues")
SECTION_TITLES = {"situation": "Situation du vendeur",
                  "diagnostic": "Diagnostic croisé",
                  "positionnement": "Positionnement concurrentiel",
                  "faiblesses": "Faiblesses récurrentes", "points_forts": "Points forts",
                  "hypotheses": "Lectures possibles de la situation",
                  "inconnues": "Ce que les données ne permettent pas de confirmer",
                  "actions": "Plan de remontée",
                  "questions": "Questions d'investigation",
                  "comparaison": "Comparaison avec la marketplace"}  # « comparaison » : analyses enregistrées avant la version « Bilan »
TYPES = {"fait", "hypothese", "inconnu"}
LEVERS = {"operationnel": "Opérationnel (préparation, remise au transporteur)", "catalogue_prix": "Catalogue et prix",
          "delai_promis": "Délai de livraison annoncé", "experience_client": "Expérience client (avis, réclamations)"}
PRIORITIES = ("haute", "moyenne", "basse")

# ----------------------------------------------------------------------------------------------------------------------------
# Consignes (françaises) : règles de fiabilité communes, style, méthode de diagnostic croisé.
# ----------------------------------------------------------------------------------------------------------------------------
RULES = """RÈGLES DE FIABILITÉ — chaque élément est contrôlé automatiquement ; tout élément qui enfreint une règle est supprimé :
1. Chiffres : uniquement ceux du paquet de preuves, recopiés à l'identique (« 57,0 % », « 114 commandes », « rang 48 sur 49 »). Aucun calcul (ni différence, ni écart en points, ni pourcentage nouveau), aucun autre arrondi. Décimales avec une virgule. Tout nombre s'écrit en chiffres (« 12 vendeurs », jamais « douze vendeurs »), pour pouvoir être vérifié.
2. Sources : chaque élément cite dans "preuves" les identifiants EXACTS du paquet (préfixes sel:, peer:, kpi:, alr:, mdl:, ord:, rev:, ctx:). N'écris jamais d'identifiant dans le texte lui-même.
3. Nature : "fait" = constat appuyé par une preuve ; "hypothese" = lecture probable, TOUJOURS au conditionnel (« il est possible que… », « cela suggère que… », « cela pourrait indiquer… ») ; "inconnu" = ce que les données ne permettent pas d'établir.
4. Aucune cause affirmée : jamais « à cause de », « dû à », « en raison de », « provoqué par », « parce que », « car », « entraîné par ». Une explication est une hypothèse au conditionnel.
5. Tu ne crées ni ne supprimes aucune alerte et ne changes aucune décision. Une alerte n'est « active » que si sa preuve alr:… l'indique pour le mois de décision ; une alerte d'un mois précédent se dit « signalée en mai » (par exemple), jamais active. Ne compte que les alertes actives. La référence des alertes est la marketplace ; les rangs dans la catégorie et parmi les concurrents directs sont descriptifs.
6. Les données ne contiennent ni publicité, ni campagne, ni promotion, ni marketing : n'en parle pas, sauf dans une question à l'utilisateur ou dans "inconnues"."""

STYLE = """STYLE — tu écris comme un stratège e-commerce senior qui accompagne un responsable des opérations :
- Phrases complètes, fluides et bienveillantes, vocabulaire métier ; jamais de reproche au vendeur ; 1 à 2 phrases par élément.
- États brésiliens toujours par leur nom complet (« São Paulo », « Minas Gerais »), jamais par leur sigle.
- Indicateurs en langage courant : « expédition tardive » (commande remise au transporteur après la date limite), « livraison en retard », « avis négatifs » (1 ou 2 étoiles), « délai annoncé au client ».
- Interdits : noms de champs ou de variables (recent_rate, known_n, p_peer, q_below_reference…), noms de tests ou de détecteurs statistiques, valeurs p ou q, style télégraphique (« remise tardive niveau : 29,6 % »).
  Écris plutôt : « Sur les trois derniers mois, 37,7 % des commandes ont été confiées au transporteur après la date limite, contre 5,2 % en moyenne sur la marketplace. »
- Les avis clients sont parfois en portugais : cite-les en les traduisant librement en français, entre guillemets, suivis de « (traduction libre) ».
- Les vendeurs se désignent par leurs 8 premiers caractères ; les catégories peuvent être nommées en français courant suivi du nom d'origine entre parenthèses."""

METHOD = """MÉTHODE — DIAGNOSTIC CROISÉ (ne te contente jamais de dire que la cause est inconnue) :
(a) Chronologie opérationnelle (évolution mensuelle kpi:history:…, alertes alr:…, volume mensuel de commandes dans sel:…) : l'expédition tardive se dégrade-t-elle avant, en même temps que, ou sans la livraison en retard ? Une hausse de l'expédition tardive sans hausse des retards de livraison suggère un problème de préparation en partie absorbé par le transporteur ; des retards de livraison sans expédition tardive orientent plutôt vers le transport ou les destinations (part des commandes hors de l'État du vendeur) ; un pic de volume peut précéder une dégradation.
(b) Voix des clients (mdl:aspects:seller:…, extraits rev:…) : quels aspects sont critiqués (livraison, qualité du produit, article erroné ou manquant, conformité à l'annonce, emballage) et que disent concrètement les clients ?
(c) Commandes concrètes (ord:…) et profil (prix, délai annoncé, part du port, positionnement peer:bench:…).
Formule ensuite la lecture LA PLUS PROBABLE, au conditionnel, en t'appuyant explicitement sur ce croisement (« la hausse simultanée des expéditions tardives et des critiques sur les articles manquants suggère que… »).
Puis signale en UNE seule phrase ce que les données de la plateforme ne peuvent pas confirmer (rupture chez un fournisseur, effectif en entrepôt, changement d'emballage…), et pose 2 ou 3 QUESTIONS D'INVESTIGATION ciblées à l'utilisateur, qui permettraient de trancher entre les lectures possibles (ex. « Le vendeur a-t-il changé de fournisseur ou d'entrepôt au printemps ? »)."""

SYSTEM = f"""Tu es un stratège e-commerce senior, chargé du suivi des vendeurs d'une marketplace (données Olist, Brésil, 2016-2018).
Tu reçois un PAQUET DE PREUVES produit par des outils déterministes (performance du vendeur, alertes, historique, positionnement concurrentiel,
avis clients, commandes problématiques). Tu en tires un « Bilan & Plan de remontée » clair et actionnable.

{RULES}

{STYLE}

{METHOD}

STRUCTURE (si "mode" vaut "remontee", le vendeur a au moins une alerte ; sinon mode "suivi" : même structure, plus courte) :
- "resume" : 2 à 3 phrases de synthèse pour un dirigeant (faits uniquement, chiffres recopiés).
- "diagnostic" : diagnostic croisé — ce qui se dégrade (niveau par rapport à la marketplace, tendance par rapport à son propre passé), à quelle étape (préparation, transport, produit) et ce qu'en disent les clients ; constats ("fait") et lectures probables ("hypothese").
- "positionnement" : rang dans la catégorie et parmi les concurrents directs, médiane et seuil du meilleur quart, profil comparé (prix, part du port, délai annoncé) ; au plus 3 concurrents nommés.
- "situation", "faiblesses", "points_forts", "hypotheses" : compléments courts ; "inconnues" : UNE phrase au plus.
- "actions" : plan de remontée — pistes concrètes pour rejoindre le meilleur quart de la catégorie, chacune STRICTEMENT au conditionnel (« une piste serait de… », « il pourrait être utile de… ») et rattachée à une faiblesse prouvée. Leviers : "operationnel" (préparation, expédition avant la date limite), "catalogue_prix" (fiches produit, prix, port), "delai_promis" (délai annoncé au regard des concurrents), "experience_client" (aspects critiqués, commandes à relire). "cible" recopie le seuil du meilleur quart présent dans les preuves (ex. « seuil du meilleur quart : 3,7 % »).
- "questions" : 2 à 3 questions d'investigation adressées à l'utilisateur.
Au plus 4 éléments par section, 5 actions, 3 questions.

Réponds UNIQUEMENT par un objet JSON de cette forme :
{{"resume": "...",
 "situation": [ITEM], "diagnostic": [ITEM], "positionnement": [ITEM], "faiblesses": [ITEM], "points_forts": [ITEM], "hypotheses": [ITEM], "inconnues": [ITEM],
 "actions": [{{"faiblesse": "...", "levier": "operationnel|catalogue_prix|delai_promis|experience_client", "action": "piste au conditionnel",
              "priorite": "haute|moyenne|basse", "cible": "...", "impact": "impact métier attendu (qualitatif)",
              "direction_attendue": "ex. moins d'expéditions tardives", "information_manquante": "...", "preuves": ["id", ...]}}],
 "questions": [{{"texte": "question se terminant par « ? »", "preuves": ["id", ...]}}]}}
avec ITEM = {{"texte": "...", "type": "fait|hypothese|inconnu", "preuves": ["id", ...]}}."""

CHAT_SYSTEM = f"""Tu es l'assistant de pilotage des vendeurs d'une marketplace (données Olist, Brésil, 2016-2018) : un stratège e-commerce senior
qui répond à un responsable des opérations au sujet d'UN vendeur, à partir du paquet de preuves uniquement (performance, alertes, historique,
positionnement concurrentiel, avis clients, commandes problématiques).

{RULES}

{STYLE}

{METHOD}

QUESTIONS FRÉQUENTES :
- « Qui sont ses concurrents directs ? » : liste des concurrents de peer:bench:… (8 premiers caractères, catégorie, volume, taux recopiés) et rang du vendeur parmi eux.
- « Pourquoi ce vendeur baisse-t-il ? » : diagnostic croisé ci-dessus, lecture la plus probable au conditionnel.
- « Que disent les avis clients ? » : aspects les plus critiqués avec leur nombre d'avis, 1 ou 2 extraits traduits, ce que cela suggère pour l'activité.
- « Comment rattraper ses concurrents ? » : seuil du meilleur quart et médiane de la catégorie, puis 2 ou 3 pistes ("piste") au conditionnel, chacune rattachée à une faiblesse prouvée.
Réponse : 2 à 6 éléments qui se lisent comme un paragraphe structuré.

Réponds UNIQUEMENT par un objet JSON :
{{"reponse": [ITEM], "questions_investigation": [{{"texte": "question à l'utilisateur, terminée par « ? »", "preuves": ["id", ...]}}],
 "questions_suivantes": ["question que l'utilisateur pourrait poser ensuite", "..."]}}
avec ITEM = {{"texte": "...", "type": "fait|hypothese|inconnu|piste", "preuves": ["id", ...]}}.
"questions_investigation" : 0 si les preuves suffisent, sinon 2 ou 3 questions ciblées pour trancher ce que les données ne confirment pas."""

MARKET_CHAT_SYSTEM = f"""Tu es l'assistant de pilotage d'une marketplace (données Olist, Brésil, 2016-2018) : un stratège e-commerce senior qui aide un
responsable des opérations à prioriser son mois. Le paquet de preuves décrit la marketplace à la fin du mois de décision : vendeurs évalués,
vendeurs en alerte classés par sévérité (alr:list:…), taux de la marketplace et catégories de produit aux taux les plus élevés sur 90 jours,
catégories comptant le plus de vendeurs en alerte (kpi:categories:…).

{RULES}

{STYLE}

QUESTIONS FRÉQUENTES :
- « Quels vendeurs nécessitent une action urgente ce mois-ci ? » : vendeurs de la liste d'alertes, d'abord sévérité élevée puis moyenne, avec l'indicateur concerné et leur taux contre la référence (recopiés) ; au plus 5 vendeurs, désignés par leurs 8 premiers caractères.
- « Quelles catégories ont le plus de retards ? » : catégories aux taux de livraison en retard les plus élevés, avec le nombre de commandes dont l'issue est connue, comparées au taux de la marketplace.
- Pour le détail d'un vendeur, invite l'utilisateur à ouvrir sa fiche d'audit.
Réponse : 2 à 6 éléments qui se lisent comme un paragraphe structuré ; toute recommandation est une "piste" au conditionnel.

Réponds UNIQUEMENT par un objet JSON :
{{"reponse": [ITEM], "questions_investigation": [{{"texte": "...?", "preuves": ["id", ...]}}], "questions_suivantes": ["...", "..."]}}
avec ITEM = {{"texte": "...", "type": "fait|hypothese|inconnu|piste", "preuves": ["id", ...]}}."""

REPAIR = """Le contrôle automatique a rejeté les éléments ci-dessous, pour les raisons indiquées. Réécris UNIQUEMENT ces éléments en corrigeant ces problèmes
(chiffres recopiés à l'identique depuis les preuves, identifiants exacts dans "preuves", conditionnel pour les hypothèses et les pistes, aucun nom de
variable ni jargon statistique, aucune cause affirmée). Si un élément ne peut pas être corrigé avec les preuves, omets-le.
Réponds UNIQUEMENT par un objet JSON de même forme que ta réponse précédente, ne contenant que les éléments corrigés.
ÉLÉMENTS REJETÉS :
"""


@dataclass
class AnalysisResult:
    model: str
    sections: dict[str, list[dict]] = field(default_factory=dict)
    actions: list[dict] = field(default_factory=list)
    questions: list[dict] = field(default_factory=list)
    resume: str | None = None
    rejected: list[dict] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    schema_ok: bool = True
    call: dict[str, Any] = field(default_factory=dict)
    mode: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def with_caveats(report: dict, evidence: list[dict]) -> list[dict]:
    """Les limites du rapport déterministe deviennent une preuve citable (ctx:limites) : leurs chiffres sont alors vérifiables."""
    if any(e["id"] == "ctx:limites" for e in evidence):
        return evidence
    return [*evidence, {"id": "ctx:limites", "kind": "fait", "source": "limites du rapport déterministe BO3", "payload": {"limites": report.get("caveats") or []}}]


def analysis_mode(report: dict) -> str:
    """« remontee » si l'audit déterministe signale au moins une alerte (niveau ou tendance), sinon « suivi »."""
    return "remontee" if (report.get("meta") or {}).get("alerts") else "suivi"


# Champs techniques retirés de ce que lit le modèle (la validation, elle, porte sur les preuves complètes) : noms de détecteurs,
# paramètres, valeurs q, définitions internes. Moins de jargon à recopier, paquet plus court.
PACKAGE_DROP = {"detector", "description", "params", "raw", "score", "test_performance", "selection", "method", "method_key", "similarity_basis",
                "definitions", "definition", "model", "severity_rule", "detectors", "persistence", "persistence_rule", "min_history", "min_recent",
                "min_own_history", "in_sample", "marketplace_calibration", "q_below_reference", "alpha", "distance", "funnel_95", "funnel_998_high",
                "baseline_label", "metric_labels", "min_known_n", "min_known_per_category", "eligible_sellers", "recent_window",
                "decision_date", "share_known_recent"}


UF_NAMES = {"AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará", "DF": "District fédéral",
            "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
            "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambouc", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
            "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins"}


def clean_payload(o: Any, key: str = "") -> Any:
    """Payload allégé pour le LLM ; les sigles d'États (champs *state) deviennent des noms complets pour que la réponse les reprenne."""
    if isinstance(o, str) and key.endswith("state") and o in UF_NAMES:
        return UF_NAMES[o]
    if isinstance(o, str):
        return o if len(o) <= 300 else o[:300] + "…"
    if isinstance(o, list):
        return [clean_payload(x, key) for x in o[:12]]
    if isinstance(o, dict):
        return {k: clean_payload(v, k) for k, v in o.items() if k not in PACKAGE_DROP}
    return o


def build_package(report: dict, evidence: list[dict], max_chars: int = 40000) -> str:
    """Paquet de preuves : contenu nettoyé des preuves (performance, alertes, historique, positionnement, avis, commandes) et rapport déterministe.
    Si le paquet est trop long : d'abord le rapport déterministe (redondant avec les preuves), puis les commandes individuelles, puis les
    preuves les moins prioritaires ; les extraits d'avis et les preuves de performance, d'alerte et de positionnement sont gardés le plus longtemps."""
    pkg = {"titre": report.get("title"), "mode": analysis_mode(report), "synthese_deterministe": report.get("narrative"),
           "rapport": {k: [ln.get("text") for ln in (report.get(k) or [])] for k in ("facts", "estimates", "similar_experiences", "actions")},
           "preuves": [{"id": e["id"], "nature": e["kind"], "contenu": clean_payload(e["payload"])} for e in evidence],
           "consigne": "pour citer les limites de la méthode, utiliser l'identifiant ctx:limites"}
    s = json.dumps(pkg, ensure_ascii=False)
    keep_last = ("peer:bench:", "alr:", "kpi:seller:", "kpi:history:", "sel:", "mdl:aspects:", "rev:", "kpi:categories:")
    while len(s) > max_chars:
        ids = [p["id"] for p in pkg["preuves"]]
        if pkg.get("rapport"):
            pkg.pop("rapport")
        elif any(i.startswith("ord:") and not i.startswith("ord:seller:") for i in ids):
            pkg["preuves"] = [p for p in pkg["preuves"] if not (p["id"].startswith("ord:") and not p["id"].startswith("ord:seller:"))]
        elif pkg["preuves"]:
            drop = next((k for k in range(len(ids) - 1, -1, -1) if not ids[k].startswith(keep_last)), len(ids) - 1)
            pkg["preuves"] = pkg["preuves"][:drop] + pkg["preuves"][drop + 1:]
        else:
            break
        s = json.dumps(pkg, ensure_ascii=False)
    return s


def parse_json(text: str) -> dict | None:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        a, b = text.find("{"), text.rfind("}")
        if a >= 0 and b > a:
            try:
                return json.loads(text[a:b + 1])
            except json.JSONDecodeError:
                return None
    return None


def _as_list(x: Any) -> list:
    return x if isinstance(x, list) else []


def _check_question(q: Any, log) -> tuple[dict | None, list[str]]:
    """Question d'investigation : texte interrogatif, chiffres et identifiants vérifiés (aucune exigence de conditionnel)."""
    if isinstance(q, str):
        q = {"texte": q, "preuves": []}
    if not isinstance(q, dict) or not isinstance(q.get("texte"), str):
        return None, ["format invalide"]
    cited = [c for c in _as_list(q.get("preuves")) if isinstance(c, str)]
    v = check_item(q["texte"], "question", cited, log)
    return ({"texte": q["texte"].strip(), "preuves": cited} if v.ok else None), v.problems


def validate_output(data: dict | None, evidence: list[dict], model: str) -> AnalysisResult:
    res = AnalysisResult(model=model)
    if not isinstance(data, dict):
        res.schema_ok = False
        res.stats = {"items_total": 0, "items_valid": 0, "items_rejected": 0}
        return res
    log = evidence_log(evidence)
    total = valid = 0
    schema_ok = True
    for sec in ITEM_SECTIONS:
        res.sections[sec] = []
        for it in _as_list(data.get(sec)):
            total += 1
            if not isinstance(it, dict) or not isinstance(it.get("texte"), str):
                schema_ok = False
                res.rejected.append({"section": sec, "item": it, "problems": ["format invalide"]})
                continue
            kind = it.get("type") if it.get("type") in TYPES else None
            cited = [c for c in _as_list(it.get("preuves")) if isinstance(c, str)]
            if kind is None:
                schema_ok = False
                res.rejected.append({"section": sec, "item": it, "problems": ["type absent ou invalide"]})
                continue
            v = check_item(it["texte"], kind, cited, log)
            if v.ok:
                valid += 1
                res.sections[sec].append({"texte": it["texte"], "type": kind, "preuves": cited})
            else:
                res.rejected.append({"section": sec, "item": it, "problems": v.problems})
    for a in _as_list(data.get("actions")):
        total += 1
        if not isinstance(a, dict) or not isinstance(a.get("action"), str):
            schema_ok = False
            res.rejected.append({"section": "actions", "item": a, "problems": ["format invalide"]})
            continue
        cited = [c for c in _as_list(a.get("preuves")) if isinstance(c, str)]
        text = " ".join(str(a.get(k) or "") for k in ("faiblesse", "action", "cible", "impact", "direction_attendue", "information_manquante"))
        v = check_item(text, "action", cited, log)  # contrôles complets : chiffres, preuves, causalité, marketing, jargon
        problems = list(v.problems)
        if not [c for c in cited if c in log.ids()]:
            problems.append("action sans preuve citée")
        if not HEDGE.search(a["action"]):
            problems.append("piste non formulée au conditionnel")
        if a.get("priorite") not in PRIORITIES:
            schema_ok = False
            problems.append("priorité invalide")
        if problems:
            res.rejected.append({"section": "actions", "item": a, "problems": problems})
        else:
            valid += 1
            res.actions.append({k: a.get(k) for k in ("faiblesse", "action", "priorite", "cible", "impact", "direction_attendue", "information_manquante")}
                               | {"levier": a.get("levier") if a.get("levier") in LEVERS else None, "preuves": cited})
    for q in _as_list(data.get("questions"))[:3]:
        total += 1
        ok, problems = _check_question(q, log)
        if ok:
            valid += 1
            res.questions.append(ok)
        else:
            res.rejected.append({"section": "questions", "item": q, "problems": problems})
    if isinstance(data.get("resume"), str) and data["resume"].strip():
        total += 1
        v = check_item(data["resume"], "resume", [], log)  # chiffres + causalité + marketing + jargon
        if v.ok:
            valid += 1
            res.resume = data["resume"].strip()
        else:
            res.rejected.append({"section": "resume", "item": data["resume"], "problems": v.problems})
    res.schema_ok = schema_ok
    res.stats = {"items_total": total, "items_valid": valid, "items_rejected": total - valid,
                 "grounding_rate": round(valid / total, 3) if total else None}
    return res


def merge_repair(first: AnalysisResult, fix: AnalysisResult) -> AnalysisResult:
    """Ajoute les éléments corrigés (validés) ; les éléments toujours rejetés restent comptés comme rejetés."""
    for sec, items in fix.sections.items():
        have = {i["texte"] for i in first.sections.get(sec, [])}
        first.sections.setdefault(sec, []).extend(i for i in items if i["texte"] not in have)
    first.actions += [a for a in fix.actions if a["action"] not in {x["action"] for x in first.actions}][: max(0, 5 - len(first.actions))]
    first.questions += [q for q in fix.questions if q["texte"] not in {x["texte"] for x in first.questions}][: max(0, 3 - len(first.questions))]
    if first.resume is None and fix.resume:
        first.resume = fix.resume
    total, first_rejected = first.stats["items_total"], len(first.rejected)
    repaired = min(first_rejected, fix.stats.get("items_valid", 0))
    valid = first.stats["items_valid"] + repaired
    if fix.stats.get("items_total"):
        first.rejected = fix.rejected  # éléments dont la correction a encore échoué (les éléments omis par le modèle restent comptés)
    first.stats = {"items_total": total, "items_valid": valid, "items_rejected": total - valid, "items_rejected_first_pass": first_rejected,
                   "items_repaired": repaired, "grounding_rate": round(valid / total, 3) if total else None}
    return first


def _repair_messages(messages: list[dict], previous: str, rejected: list[dict]) -> list[dict]:
    body = json.dumps([{"section": r.get("section", "reponse"), "element": r.get("item"), "problemes": r.get("problems")} for r in rejected],
                      ensure_ascii=False)[:8000]
    return [*messages, {"role": "assistant", "content": previous}, {"role": "user", "content": REPAIR + body}]


def analyse(provider: LLMProvider, report: dict, evidence: list[dict], repair: bool = True) -> AnalysisResult:
    evidence = with_caveats(report, evidence)
    package = build_package(report, evidence)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": "PAQUET DE PREUVES :\n" + package}]
    t0 = time.time()
    out = provider.complete(messages, max_tokens=7000)
    res = validate_output(parse_json(out.content), evidence, getattr(out, "model_used", "") or provider.model)
    calls, repair_model = 1, None
    if repair and res.rejected:
        try:
            fix_out = provider.complete(_repair_messages(messages, out.content, res.rejected), max_tokens=4000)
            calls += 1
            repair_model = getattr(fix_out, "model_used", "") or fix_out.model_returned
            fix = validate_output(parse_json(fix_out.content), evidence, provider.model)
            res = merge_repair(res, fix)
        except LLMError:
            pass  # la première passe validée reste affichée
    res.mode = analysis_mode(report)
    res.model = getattr(out, "model_used", "") or out.model_returned
    res.call = {"model_requested": out.model_requested, "model_returned": out.model_returned, "model_used": res.model,
                "candidates_tried": getattr(out, "candidates_tried", []), "repair_model_used": repair_model, "latency_s": out.latency_s,
                "usage": out.usage, "cost": out.cost, "cached": out.cached, "attempts": out.attempts, "wall_s": round(time.time() - t0, 2),
                "package_chars": len(package), "llm_calls": calls}
    return res


def revalidate(ai: dict, report: dict, evidence: list[dict]) -> dict:
    """Analyse enregistrée (fichier) revalidée avec les règles ACTUELLES avant tout réemploi (PDF) : un élément accepté par une version
    antérieure du contrôle mais refusé aujourd'hui n'est plus montré."""
    data = {**(ai.get("sections") or {}), "actions": ai.get("actions") or [], "questions": ai.get("questions") or [], "resume": ai.get("resume")}
    res = validate_output(data, with_caveats(report, evidence), ai.get("model", ""))
    return {**ai, "sections": res.sections, "actions": res.actions, "questions": res.questions, "resume": res.resume}


# ----------------------------------------------------------------------------------------------------------------------------
# Assistant (vendeur ou marketplace)
# ----------------------------------------------------------------------------------------------------------------------------
CHAT_TYPES = TYPES | {"piste"}


def check_chat_item(text: str, kind: str, cited: list[str], log) -> "object":
    """Une « piste » du chat suit les règles d'une action : preuve obligatoire et formulation conditionnelle."""
    if kind != "piste":
        return check_item(text, kind, cited, log)
    v = check_item(text, "action", cited, log)
    if not [c for c in cited if c in log.ids()]:
        v.problems.append("piste sans preuve citée")
    if not HEDGE.search(text or ""):
        v.problems.append("piste non formulée au conditionnel")
    v.ok = not v.problems
    return v


def _validate_chat(data: dict | None, log) -> tuple[list[dict], list[dict], list[dict]]:
    items, questions, rejected = [], [], []
    for it in _as_list((data or {}).get("reponse")):
        if not isinstance(it, dict) or it.get("type") not in CHAT_TYPES or not isinstance(it.get("texte"), str):
            rejected.append({"section": "reponse", "item": it, "problems": ["format invalide"]})
            continue
        cited = [c for c in _as_list(it.get("preuves")) if isinstance(c, str)]
        v = check_chat_item(it["texte"], it["type"], cited, log)
        if v.ok:
            items.append({"texte": it["texte"], "type": it["type"], "preuves": cited})
        else:
            rejected.append({"section": "reponse", "item": it, "problems": v.problems})
    for q in _as_list((data or {}).get("questions_investigation"))[:3]:
        ok, problems = _check_question(q, log)
        if ok:
            questions.append(ok)
        else:
            rejected.append({"section": "questions_investigation", "item": q, "problems": problems})
    return items, questions, rejected


def _chat(provider: LLMProvider, system: str, report: dict | None, evidence: list[dict], history: list[dict], question: str,
          package_fn: Callable[[], str], repair: bool = True) -> dict:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": "PAQUET DE PREUVES :\n" + package_fn()}]
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            msgs.append({"role": h["role"], "content": h["content"][:2000]})
    msgs.append({"role": "user", "content": question})
    out = provider.complete(msgs, max_tokens=3000)
    data = parse_json(out.content)
    log = evidence_log(evidence)
    items, questions, rejected = _validate_chat(data, log)
    first_rejected = len(rejected)
    if repair and rejected and isinstance(data, dict):
        try:
            fix_out = provider.complete(_repair_messages(msgs, out.content, rejected), max_tokens=2000)
            f_items, f_questions, f_rejected = _validate_chat(parse_json(fix_out.content), log)
            items += [i for i in f_items if i["texte"] not in {x["texte"] for x in items}]
            questions += [q for q in f_questions if q["texte"] not in {x["texte"] for x in questions}][: max(0, 3 - len(questions))]
            rejected = f_rejected if parse_json(fix_out.content) is not None else rejected
        except LLMError:
            pass
    follow = [q for q in _as_list((data or {}).get("questions_suivantes")) if isinstance(q, str) and 3 <= len(q) <= 300][:3]
    cited = {c for x in items + questions for c in x["preuves"]}
    return {"model": getattr(out, "model_used", "") or out.model_returned, "items": items, "questions": questions, "rejected": rejected, "follow_up": follow,
            "schema_ok": isinstance(data, dict), "stats": {"rejected_first_pass": first_rejected, "rejected": len(rejected)},
            "evidence": [e for e in evidence if e["id"] in cited],
            "call": {"latency_s": out.latency_s, "usage": out.usage, "cost": out.cost, "cached": out.cached, "model_returned": out.model_returned,
                     "model_used": getattr(out, "model_used", "") or out.model_returned, "candidates_tried": getattr(out, "candidates_tried", [])}}


def chat(provider: LLMProvider, report: dict, evidence: list[dict], history: list[dict], question: str) -> dict:
    """Assistant sur UN vendeur : toutes les preuves de l'audit (performance, alertes, historique, positionnement, avis, commandes)."""
    evidence = with_caveats(report, evidence)
    return _chat(provider, CHAT_SYSTEM, report, evidence, history, question, lambda: build_package(report, evidence))


def market_package(evidence: list[dict], month: str | None) -> str:
    return json.dumps({"contexte": f"marketplace, décision fin {month}", "preuves": [{"id": e["id"], "nature": e["kind"], "contenu": clean_payload(e["payload"])}
                                                                                   for e in evidence]}, ensure_ascii=False)[:40000]


def market_chat(provider: LLMProvider, evidence: list[dict], month: str | None, history: list[dict], question: str) -> dict:
    """Assistant « marketplace » (tableau de bord, annuaire, alertes) : alertes prioritaires et catégories les plus touchées du mois."""
    return _chat(provider, MARKET_CHAT_SYSTEM, None, evidence, history, question, lambda: market_package(evidence, month))


__all__ = ["AnalysisResult", "LEVERS", "LLMError", "SECTION_TITLES", "analyse", "analysis_mode", "build_package", "chat", "check_chat_item",
           "market_chat", "merge_repair", "parse_json", "revalidate", "validate_output"]
