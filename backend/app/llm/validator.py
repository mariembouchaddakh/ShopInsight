"""Validation des sorties LLM contre le journal de preuves (aucun contenu non validé n'est affiché).

Pour chaque élément produit par le modèle :
  * tout nombre doit exister dans les preuves déterministes (core.verify_narrative, via verify_bo3_narrative) ;
  * tout identifiant de preuve cité doit exister ;
  * un « fait » doit citer au moins une preuve ;
  * une « hypothèse » doit être formulée comme telle (pourrait, possible, à vérifier…) ;
  * aucune affirmation causale hors hypothèse prudente ; aucun contenu marketing / publicité (données absentes d'Olist) hors « inconnu ».
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

from ..config import ROOT

sys.path.insert(0, str(ROOT / "src"))
from agents.bo3_support import verify_bo3_narrative  # noqa: E402
from agents.core import FACT, EvidenceLog  # noqa: E402

HEDGE = re.compile(r"\b(peut|peuvent|pourrai\w*|possible\w*|hypoth\w*|probable\w*|semble\w*|sugg[eè]r\w*|à vérifier|à confirmer|"
                   r"éventuel\w*|plausible\w*|il se peut|serait|seraient|piste\w*|envisage\w*|conviendrai\w*|gagnerai\w*)\b", re.I)
CAUSAL = re.compile(r"\b(car|à cause d[eu]|causé\w* par|a causé|cause[snt]? principale|parce qu|c'est dû|est dû|sont dus|en raison d[eu]|provoqu\w*|"
                    r"entraîn\w* par|résult\w* de)\b", re.I)
MARKETING = re.compile(r"\b(publicit\w*|campagne\w*|marketing|promotion\w*|réseaux sociaux|influenceu\w*|référencement payant|budget publicitaire)\b", re.I)
YEAR = re.compile(r"\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)?\s*20(?:1[6-9])\b", re.I)
EVIDENCE_REF = re.compile(r"\b(?:ord|rev|kpi|mdl|ctx|sel|peer|alr):[\w:.\-]+")
# Jargon statistique interne : jamais montré à un lecteur métier (noms de détecteurs, valeurs p / q).
JARGON = re.compile(r"(b[êe]ta[- ]?binomial\w*|benjamini|hochberg|\bcusum\b|\bewma\b|valeur[s]?[- ]p\b|p[- ]valeur\w*|q[- ]valeur\w*|\bq\s*[<=>]|"
                    r"\bbinomial\w*|a posteriori|\bknn\b|k plus proches voisins)", re.I)
# Séparateur de milliers à la française (« 17 449 », espace fine ou insécable) : regroupé avant la vérification des chiffres.
THOUSANDS = re.compile(r"(?<![\d,.])\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?![\d])")
SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
# Identifiant recopié depuis un gabarit (« ord:… », « peer:bench:... », « rev:<id> ») : ne désigne aucune preuve vérifiable.
PLACEHOLDER_REF = re.compile(r"\b(?:ord|rev|kpi|mdl|ctx|sel|peer|alr):[\w:.\-]*?(?:…|\.\.\.|<)")


@dataclass
class Verdict:
    ok: bool
    problems: list[str] = field(default_factory=list)


def evidence_log(evidence: list[dict]) -> EvidenceLog:
    """Reconstruit le journal de preuves à partir de la réponse de l'API, plus les constantes de méthode (fenêtres)."""
    log = EvidenceLog()
    for e in evidence:
        log.add(e["id"], e.get("kind", FACT), e.get("source", ""), e.get("payload") if isinstance(e.get("payload"), dict) else {"value": e.get("payload")})
    log.add("ctx:methode", FACT, "constantes de la méthode BO3",
            {"fenetre_recente_jours": 90, "historique_mois": 12, "historique_jours": 365, "verite_future_jours": 60})
    return log


def technical_keys(log: EvidenceLog) -> set[str]:
    """Noms de champs des preuves (« recent_rate », « q_below_reference »…) : des noms de variables, jamais du texte pour un lecteur.
    Les VALEURS (ex. catégorie « computers_accessories ») restent autorisées."""
    cached = getattr(log, "_technical_keys", None)
    if cached is not None:
        return cached
    keys: set[str] = set()

    def walk(x) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(k, str) and "_" in k:
                    keys.add(k.lower())
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    for e in log.with_prefix(""):
        walk(e.payload)
    log._technical_keys = keys  # type: ignore[attr-defined]
    return keys


def check_item(text: str, kind: str, cited: list[str], log: EvidenceLog) -> Verdict:
    """kind : fait | hypothese | inconnu | action | resume | question."""
    problems: list[str] = []
    body = THOUSANDS.sub(lambda m: re.sub(r"[ \u00a0\u202f]", "", m.group(0)), YEAR.sub(" ", text or ""))
    ok, p = verify_bo3_narrative(body, log)
    problems += p
    tech = sorted({t for t in SNAKE.findall((text or "").lower()) if t in technical_keys(log)})
    if tech:
        problems.append(f"nom de variable technique : {', '.join(tech)}")
    if JARGON.search(text or ""):
        problems.append(f"jargon statistique : {JARGON.search(text or '').group(0)}")
    for ref in cited:
        if ref not in log.ids():
            problems.append(f"preuve inconnue : {ref}")
    for ref in PLACEHOLDER_REF.findall(text or ""):
        problems.append(f"identifiant de preuve incomplet (gabarit recopié) : {ref}")
    if kind == "fait" and not [c for c in cited if c in log.ids()] and not EVIDENCE_REF.search(text or ""):
        problems.append("fait sans preuve citée")
    if kind == "hypothese" and not HEDGE.search(text or ""):
        problems.append("hypothèse non formulée comme telle")
    if kind == "question" and not (text or "").rstrip().endswith("?"):
        problems.append("question sans point d'interrogation")
    # Une question n'affirme rien : elle peut évoquer une cause ou une donnée absente d'Olist (promotion, stock…) pour la faire vérifier.
    if CAUSAL.search(text or "") and not (kind == "hypothese" and HEDGE.search(text or "")) and kind not in ("inconnu", "question"):
        problems.append("affirmation causale non prudente")
    if MARKETING.search(text or "") and kind not in ("inconnu", "question"):
        problems.append("marketing / publicité : non couvert par les données Olist")
    if not (text or "").strip():
        problems.append("texte vide")
    return Verdict(not problems, problems)
