# Agent OM5 — Autonomous KPI Monitoring and Multi-Agent Reporting

## Version LangGraph

L'entrée publique reste `ReportingAgent.run(month, mode, include_agents)`. `OM5State` transporte période, mode, KPI, comparaisons, anomalies, segments, plan, résultats BO1–BO3, preuves, trace, priorités, rapport, erreurs, compteur de correction et statut partiel.

Routage: BO1 pour `late_rate`, `late_handover_rate`, `delivery_duration_mean_days`; BO2 pour `late_rate`, `poor_review_rate`, `average_review_score`; BO3 pour `late_rate`, `poor_review_rate`, `late_handover_rate`.

Gemini ne choisit ni outil ni agent. Il rédige à partir du contexte validé et ne peut modifier les tables KPI ni les scores. Une sortie acceptée porte `generation_mode=gemini` et `validation_status=valid`; sinon le rapport déterministe est finalisé avec la cause du repli.

`ReportingAgent` est l'orchestrateur global ShopInsight. Ses calculs restent déterministes; il n'utilise pas de LLM pour calculer, détecter ou décider qu'une anomalie existe.

## Outils

| Outil | Entrée | Sortie | Preuve |
|---|---|---|---|
| `get_monthly_kpis` | mois, mode | valeurs, unités, numérateur/dénominateur | `om5:kpi:*` |
| `compare_periods` | mois, mode | MoM, fenêtre, annuel | `om5:comparison:*` |
| `detect_kpi_anomalies` | mois, mode | méthode, effectif, q/MAD, sévérité | `om5:anomaly:*` |
| `analyze_segments` | mois, KPI, mode | États/catégories, volume, suffisance | `om5:segments:*` |
| `collect_bo1_insights` | période | triage public BO1 | `om5:bo1:*` |
| `collect_bo2_insights` | mois, focus | rapport public BO2 | `om5:bo2:*` |
| `collect_bo3_insights` | mois | brief marketplace BO3 | `om5:bo3:*` |

## Politique de planification

- Logistique dégradée : segments, BO1, BO2 et BO3.
- Satisfaction dégradée : BO2 et BO3.
- Activité en baisse : catégories et États.
- Aucun signal : rapport standard, aucun appel collaborateur.

Le budget est huit appels, y compris les outils locaux. Deux anomalies au plus déclenchent une segmentation détaillée dans une exécution, afin de conserver de la capacité aux agents spécialisés. Les résultats absents produisent un rapport partiel explicite.

## Types d'affirmations

- `fait` : KPI calculé depuis Silver/Gold.
- `estimation` : anomalie, comparaison, signal BO1/BO2/BO3.
- `action` : hypothèse opérationnelle à valider, toujours reliée au signal.

Le validateur refuse une référence inexistante, un KPI incomplet, une division par zéro matérialisée ou une formulation causale non encadrée.

