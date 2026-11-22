"""Cas de référence pour évaluer l'analyse IA (≈ 20 vendeurs réels, choix DÉTERMINISTE, aucune évaluation humaine fabriquée).

    python -m backend.app.llm.reference_cases --project-dir .

Six situations (décisions TEST 2018-06, puis 2018-05, 2018-04 si besoin) choisies par règles fixes sur les sorties de BO3 :
  persistent     alerte de niveau ce mois ET le mois précédent
  recent         alerte de niveau ce mois, aucune alerte sur ce vendeur les 3 mois précédents
  weak_trend     alerte de tendance seulement (signal faible)
  mixed          avis 1-2 en alerte avec critiques partagées entre plusieurs aspects
  insufficient   vendeur actif mais volume insuffisant pour toute alerte
  strong         points forts sur au moins 2 indicateurs et aucune alerte
Sorties : docs/reference_cases/cases.json, cases.md, review_form.csv (à remplir par l'équipe), rubric.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from agents.bo3_agent import SellerAuditAgent  # noqa: E402

QUOTAS = {"persistent": 4, "recent": 4, "weak_trend": 3, "mixed": 3, "insufficient": 3, "strong": 3}
LABELS = {"persistent": "Sous-performance persistante", "recent": "Dégradation récente", "weak_trend": "Signal de tendance faible",
          "mixed": "Plaintes mixtes", "insufficient": "Preuves insuffisantes", "strong": "Bonne performance"}
CRITERIA = ["adherence_preuves", "coherence_factuelle", "profondeur_analytique", "separation_faits_hypotheses",
            "pertinence_recommandations", "actionnabilite", "completude", "clarte"]
UNSUPPORTED_COMMON = ["toute cause présentée comme certaine (Olist n'enregistre pas les causes)",
                      "tout chiffre absent des preuves ou recalculé",
                      "toute affirmation sur la publicité, les campagnes, les promotions ou le marketing du vendeur",
                      "toute pratique attribuée aux concurrents ou aux « meilleurs vendeurs » sans preuve",
                      "toute prédiction sur l'avenir du vendeur présentée comme certaine"]
EXPECTED_RECO = {
    "persistent": "priorité haute sur l'indicateur en alerte depuis plusieurs mois ; contact du vendeur ; actions liées à l'indicateur (préparation / remise si remise tardive)",
    "recent": "vérifier si le signal se confirme ; contact préventif ; surveiller le mois suivant",
    "weak_trend": "présenter l'alerte de tendance comme un signal faible ; recouper avec le niveau ; pas d'action lourde",
    "mixed": "distinguer livraison et produit ; orienter vers logistique ET catalogue / préparation",
    "insufficient": "dire qu'aucune conclusion n'est possible ; recommander un suivi au niveau global, pas de sanction",
    "strong": "souligner les points forts observés sans en tirer de cause ; pas d'action corrective inventée",
}


MONTHS = ["2018-06", "2018-05", "2018-04"]  # période TEST, du plus récent au plus ancien


def pick(ag: SellerAuditAgent) -> dict[str, list[tuple[str, str]]]:
    """Remplit les quotas mois par mois (juin, puis mai, puis avril 2018) ; un vendeur n'apparaît qu'une fois."""
    H, A = ag.monthly, ag.history
    out: dict[str, list[tuple[str, str]]] = {k: [] for k in QUOTAS}
    used: set[str] = set()
    for month in MONTHS:
        cur = H[H["month"] == month]
        prev_m = str(pd.Period(month, "M") - 1)
        first_m = str(pd.Period(month, "M") - 3)
        lvl_now = set(cur.loc[cur["alert_level"], "seller_id"])
        lvl_prev = set(H.loc[(H["month"] == prev_m) & H["alert_level"], "seller_id"])
        recent_hist = set(A.loc[(A["month"] >= first_m) & (A["month"] <= prev_m) & (A["status"] != "resolved"), "seller_id"])
        trend_now = set(cur.loc[cur["alert_trend"], "seller_id"])
        g = cur.groupby("seller_id")
        strengths = g["strength"].sum()
        any_alert = g.apply(lambda x: bool((x["alert_level"] | x["alert_trend"]).any()), include_groups=False)
        eligible_any = g["eligible"].any()
        big = g["rec_n"].max()
        order = lambda s_: (-int(big.get(s_, 0)), s_)  # noqa: E731

        def take(key, pool, sort=order):
            for s_ in sorted((x for x in pool if x not in used), key=sort):
                if len(out[key]) >= QUOTAS[key]:
                    break
                out[key].append((s_, month))
                used.add(s_)

        take("persistent", lvl_now & lvl_prev)
        take("recent", lvl_now - lvl_prev - recent_hist)
        take("weak_trend", trend_now - lvl_now)
        if len(out["mixed"]) < QUOTAS["mixed"]:
            mixed = []
            for s_ in sorted((lvl_now | trend_now) - used, key=order):
                v = ag.seller_voice(s_, month)
                neg = [r["negative"] for r in v.get("top_negative", [])]
                if len(neg) >= 2 and neg[0] >= 5 and neg[1] >= 0.5 * neg[0]:
                    mixed.append(s_)
            take("mixed", mixed, sort=lambda s_: mixed.index(s_))
        take("insufficient", [s_ for s_ in any_alert.index if not eligible_any[s_] and int(big.get(s_, 0)) >= 3])
        take("strong", [s_ for s_ in strengths.index if strengths[s_] >= 2 and not any_alert[s_]])
    return out


def case_record(ag: SellerAuditAgent, case_id: str, category: str, seller: str, month: str) -> dict:
    rep = ag.audit(seller, month, use_llm=False)
    key_lines = [l.text for l in rep.estimates if l.text.startswith(("ALERTE", "Point fort", "Signal")) or "volume insuffisant" in l.text]
    hyps = [l.text for l in rep.actions if l.evidence]
    return {"case_id": case_id, "category": category, "category_label": LABELS[category], "seller_id": seller, "month": month,
            "seller_context": rep.facts[0].text if rep.facts else "",
            "deterministic_evidence": [l.text for l in rep.facts[1:6]],
            "expected_observations": key_lines or [rep.narrative],
            "supported_hypotheses": hyps or ["aucune hypothèse d'action particulière : surveillance standard"],
            "unsupported_explanations": UNSUPPORTED_COMMON,
            "expected_recommendation": EXPECTED_RECO[category],
            "deterministic_narrative": rep.narrative}


RUBRIC = """# Grille d'évaluation des analyses IA (revue humaine)

Chaque analyse IA (cas × modèle) est notée de 1 (très insuffisant) à 5 (excellent) sur 8 critères, en la comparant au rapport déterministe
du même cas (`cases.md`). **Les chiffres et les alertes ne sont pas à juger** : ils sont vérifiés automatiquement contre les preuves.

| Critère | 1 | 3 | 5 |
|---|---|---|---|
| adherence_preuves | affirmations sans lien avec les preuves | la plupart reliées | tout est relié aux preuves citées |
| coherence_factuelle | contredit le rapport déterministe | approximations | fidèle au rapport |
| profondeur_analytique | paraphrase | quelques liens entre indicateurs | met en relation indicateurs, évolution et avis |
| separation_faits_hypotheses | hypothèses présentées comme des faits | séparation partielle | séparation nette et prudente |
| pertinence_recommandations | sans rapport avec la situation | génériques | ciblées sur les faiblesses du cas |
| actionnabilite | inapplicables | vagues | concrètes, priorisées, avec l'information à obtenir |
| completude | oublie l'essentiel | couvre l'alerte principale | couvre alertes, points forts, limites, inconnues |
| clarte | confus | lisible | clair, concis, sans jargon |

Colonnes supplémentaires : `affirmation_causale_non_etayee` (oui/non), `hallucination` (oui/non : fait inventé ou contredit), `commentaire`.
Le juge automatique (troisième modèle) remplit les mêmes critères dans `quality/llm_benchmark.json` ; la comparaison juge / humain se fait
avec `python -m backend.app.llm.benchmark --compare-human docs/reference_cases/review_form.csv` une fois le formulaire rempli.
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-dir", type=Path, default=ROOT)
    a = ap.parse_args()
    ag = SellerAuditAgent(a.project_dir)
    picked = pick(ag)
    cases, n = [], 0
    for cat in QUOTAS:
        for s, month in picked[cat]:
            n += 1
            cases.append(case_record(ag, f"RC{n:02d}", cat, s, month))
    out = a.project_dir / "docs/reference_cases"
    out.mkdir(parents=True, exist_ok=True)
    (out / "cases.json").write_text(json.dumps({"months": MONTHS, "selection_rules": __doc__, "cases": cases}, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Cas de référence ({len(cases)} vendeurs, décisions TEST avr.–juin 2018)", "",
          "Choisis par règles fixes sur les sorties de BO3 (voir `backend/app/llm/reference_cases.py`). **Aucune évaluation humaine n'est pré-remplie.**", ""]
    for c in cases:
        md += [f"## {c['case_id']} — {c['category_label']} — vendeur `{c['seller_id']}` — décision fin {c['month']}", "", f"**Contexte** : {c['seller_context']}", "",
               "**Observations attendues (déterministes)** :", *[f"- {x}" for x in c["expected_observations"]], "",
               "**Hypothèses étayées** :", *[f"- {x}" for x in c["supported_hypotheses"]], "",
               "**Explications non étayées (à pénaliser)** :", *[f"- {x}" for x in c["unsupported_explanations"]], "",
               f"**Recommandation attendue** : {c['expected_recommendation']}", ""]
    (out / "cases.md").write_text("\n".join(md), encoding="utf-8")
    (out / "rubric.md").write_text(RUBRIC, encoding="utf-8")
    with (out / "review_form.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["case_id", "category", "seller_id", "month", "model", *CRITERIA, "affirmation_causale_non_etayee", "hallucination", "commentaire", "relecteur"])
        for c in cases:
            for model in ("a", "b"):
                w.writerow([c["case_id"], c["category"], c["seller_id"], c["month"], model, *[""] * len(CRITERIA), "", "", "", ""])
    print(json.dumps({k: [m for _, m in v] for k, v in picked.items()}), "->", out)


if __name__ == "__main__":
    main()
