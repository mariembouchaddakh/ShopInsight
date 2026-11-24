# Guide d'intégration OM5 pour Mariem

## Branches et fichiers

- Base : `origin/bo3-seller-platform` (`382fd44`).
- Contribution : `om5-reporting-agent`.
- Fichiers partagés modifiés : `backend/app/main.py`, `backend/app/registry.py`, `src/agents/__init__.py`, `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, `frontend/src/components/app/shell.tsx`, `README.md`.
- Les autres fichiers OM5 sont isolés sous `src/agents/om5_*`, `backend/app/routers/om5.py`, `frontend/src/pages/om5.tsx`, `tests/`, `docs/` et `quality/`.

Risque principal de conflit : navigation React, inclusion des routeurs et registre. Résoudre en conservant les ajouts OM5 dans les listes existantes, sans remplacer les entrées BO3.

## Installation et données

```powershell
pip install -r requirements.txt -r requirements-agents.txt -r requirements-api.txt
cd frontend
npm ci
cd ..
python src/prepare_data.py --source-zip data/raw/olist_brazilian_ecommerce.zip --project-dir .
python src/validate_outputs.py --project-dir .
```

Pour l'intégration BO1/BO3 seulement si les artefacts sont absents :

```powershell
python src/build_model_features.py --project-dir .
python src/train_agent_models.py --project-dir .
python src/build_seller_panel.py --project-dir .
python src/train_seller_models.py --project-dir .
```

`data/`, les modèles et `.env` restent ignorés par Git.

## Exécution

```powershell
uvicorn backend.app.main:app --port 8000
cd frontend; npm run dev
python src/run_om5.py --month 2018-03 --mode as_of --with-agents
python src/run_om5.py --months 2018-01,2018-02,2018-03 --output-dir reports/om5
```

Le scheduler externe peut exécuter la CLI; aucun scheduler interne n'est activé. Réexécuter le même mois remplace uniquement les fichiers nommés pour ce mois/mode, ce qui rend le replay idempotent.

## Tests et évaluation

```powershell
python -m unittest tests.test_om5 tests.test_om5_temporal tests.api.test_om5 -v
python -m unittest discover -s tests -v
python src/evaluate_om5.py --project-dir .
cd frontend; npm run build
```

Résultats attendus de cette branche : 126/126 concordances KPI, invariance temporelle vraie, 15 tests OM5 réussis et build Vite réussi. Les résultats exacts sont dans `quality/om5_evaluation_report.md`.

## API

La documentation interactive est `/docs`. Les endpoints OM5 sont sous `/api/om5`. `mode=as_of` est le défaut. `include_agents=false` permet une réponse plus rapide et strictement KPI; `true` active les appels dynamiques uniquement en présence d'un signal.

## Intégration et rollback

1. Mettre à jour la branche cible BO3.
2. Fusionner ou cherry-pick les commits OM5 dans une branche d'intégration.
3. Résoudre les trois listes partagées (routeurs, registre, navigation) sans supprimer les ajouts récents.
4. Reconstruire les données ignorées et lancer tests/build.
5. Vérifier `/api/om5/meta`, `/api/om5/report?month=2018-03` et `/om5`.

Rollback : revert des commits OM5. Aucune migration de base de données ni modification des données sources n'est nécessaire.

