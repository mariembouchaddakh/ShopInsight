# Grille d'évaluation des analyses IA (revue humaine)

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
