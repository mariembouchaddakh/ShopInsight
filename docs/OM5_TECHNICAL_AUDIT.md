# Audit technique OM5

## Portée de l'audit

Base inspectée : `origin/bo3-seller-platform` au commit `382fd44`, après comparaison avec `origin/main` (`be0ba36`). La branche BO3 est la bonne base car elle contient FastAPI, React, les exports ReportLab, le registre d'agents, la couche LLM facultative et l'agent vendeur. Les sources officielles consultées sont le README, le notebook de préparation, le classeur Phase 2, le dictionnaire des données et le dossier technique PDF.

L'exigence officielle OM5 est : **« automatiser les KPI, les dashboards et le reporting »**. Les tables Gold mensuelles, le dashboard général et des exports vendeur existaient déjà. Le monitoring statistique global, l'intégrité `as_of`, la planification multi-agent et le rapport marketplace sont des contributions complémentaires de cette branche, pas des DSO officiels retrouvés dans les documents.

## Matrice de traçabilité

| Exigence OM5 | Fonctionnalité existante | Fichier / fonction | Lacune constatée | Contribution OM5 |
|---|---|---|---|---|
| KPI mensuels | Agrégats marketplace, État, catégorie | `src/prepare_data.py::aggregate_kpis`, `build_metric_catalog` | Gold rétrospectif seulement | Moteur `as_of` et rétrospectif, métadonnées et preuves |
| Dashboard | Dashboard BO3 vendeur | `frontend/src/pages/dashboard.tsx` | Pas de page monitoring marketplace | Page `/om5` dédiée, sans remplacer BO3 |
| Reporting | PDF/CSV par vendeur | `backend/app/reports.py` | Pas de rapport global marketplace | PDF, JSON, KPI CSV, preuves CSV distincts |
| Intégrité temporelle | BO1/BO3 appliquent des dates de décision | `bo1_agent.py`, `bo3_sellers.py::decision_date` | KPI Gold utilise les issues finales | Recalcul Silver à la date T et tests d'invariance |
| Anomalies KPI | Détecteurs vendeur BO3 | `bo3_sellers.py` (Wilson, BH, CUSUM, EWMA) | Pas de monitoring des séries globales | MAD robuste et tests de proportions réutilisant Wilson/BH |
| Segments | Tables Gold État/catégorie | `DataStore.state_monthly/category_monthly` | Pas d'attribution de variation | Contributions volume/taux, seuil d'effectif, avertissement causal |
| Multi-agents | Registre avec verrou par agent | `backend/app/registry.py` | Aucun orchestrateur global | Plan dynamique OM5 et capture de preuve sous verrou |
| Preuves | `EvidenceLog`, `verify_narrative` | `src/agents/core.py` | Un chiffre pouvait seulement exister « quelque part » | Validation KPI/unité/période/dénominateur/référence/causalité |
| Sans LLM | Fallbacks BO1–BO3 | Agents et `backend/app/llm` | Aucun agent OM5 | Workflow entièrement déterministe; LLM non requis |
| Automatisation | Génération à la demande | API existante | Pas de batch/replay OM5 | CLI mono-mois ou batch, sorties idempotentes par nom |

## Éléments réutilisés

- `DataStore`, `Tool`, `EvidenceLog`, `Evidence`, `Line`, `Report` et la sérialisation existante.
- Tables Silver/Gold produites par `prepare_data.py`; aucun second pipeline Raw → Gold.
- Wilson et Benjamini–Hochberg de BO3; aucune copie des détecteurs vendeur.
- Méthodes publiques `triage`, `report` et `marketplace_brief` sans modification métier.
- `AgentRegistry` et ses verrous, appelés séquentiellement pour éviter les interblocages.
- ReportLab, Tailwind, TanStack Query et Recharts déjà présents.

## Données auditées

Le dataset Kaggle public a été téléchargé dans `data/raw` (ignoré par Git). L'archive SHA-256 et les neuf fichiers correspondent aux empreintes attendues. Le pipeline a produit 99 441 commandes, 21 mois complets, 16 253 lignes vendeur-mois et a réussi 39/39 contrôles. `validate_outputs.py` a réussi ses 17 contrôles indépendants.

Les artefacts BO1 et BO3 étaient absents. Ils ont été reconstruits uniquement parce qu'ils étaient nécessaires aux tests d'intégration multi-agents; les résultats de référence déjà versionnés ont été réutilisés et aucune donnée/modèle n'est ajoutée à Git.

## Risques et décisions

- La valeur des articles est toujours nommée ainsi, jamais « bénéfice » ou « chiffre d'affaires net ».
- Les commandes multi-vendeurs comptent une seule fois au niveau marketplace; les KPI vendeur existants les excluent.
- Les mois incomplets ne servent pas aux tendances/détecteurs.
- Les issues inconnues à T sont exclues des numérateurs et dénominateurs `as_of`.
- Olist n'a pas de labels d'anomalie KPI : aucune précision/rappel historique fictifs ne sont publiés.

