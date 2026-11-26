# Évaluation OM5 — données Olist authentiques

## Périmètre

Le pipeline est évalué sur les 99 441 commandes Olist. Les mois TEST 2018-04 à 2018-06 sont réservés à la lecture finale. Olist ne fournit aucune vérité terrain d'anomalie KPI : les métriques supervisées ci-dessous concernent uniquement des perturbations injectées et reproductibles.

## Validation des KPI

- Concordance Gold : 126/126 (100.0%).
- Invariance après suppression des événements futurs : True.
- Division par zéro → valeur nulle : True.

## Détecteurs — simulation séparée des observations

| Amplitude injectée | Essais positifs | Précision baseline | Rappel baseline | F1 baseline | Précision OM5 | Rappel OM5 | F1 OM5 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| +5 pp | 9 | 0.750 | 1.000 | 0.857 | 1.000 | 1.000 | 1.000 |
| +10 pp | 9 | 0.750 | 1.000 | 0.857 | 1.000 | 1.000 | 1.000 |
| +20 pp | 9 | 0.750 | 1.000 | 0.857 | 1.000 | 1.000 | 1.000 |

Le taux d'alertes sur l'historique non étiqueté est descriptif et ne doit pas être nommé taux de faux positifs. Les simulations modifient les compteurs du taux de retard sur plusieurs mois, amplitudes et graines.

## Évaluation agentique

- Citations valides : 100%.
- Fonctionnement sans LLM : True.
- Latence froide du scénario mars 2018 : 5.030 s.
- Agent indisponible : rapport partiel conservé et erreurs tracées (3).

## Limites

- Seulement 21 mois complets : une méthode robuste et parcimonieuse est préférable aux modèles temporels complexes.
- Les injections testent la sensibilité, pas la validité causale des alertes historiques.
- L'ablation LLM n'est pas exécutée sans clé; OM5 reste intégralement déterministe.
