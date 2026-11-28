# Agents BO1 et BO2 — REHEARSE

Ces deux agents réalisent les DSO agentiques **DS1.3** (diagnostic préventif) et **DS2.3** (voix du client) du plan à 15 DSO. Ils respectent la règle du projet : *chaque agent sépare les faits observés, les estimations du modèle et les expériences d'autres clients, et cite les enregistrements utilisés.*

## 1. Architecture commune (`src/agents/core.py`)

```
question ─► planificateur ─► OUTILS (Python, déterministes) ─► EvidenceLog (preuves numérotées)
              │ (règles, ou LLM via vLLM)                              │
              └────────────────────────────────────────────────────────┴─► composeur déterministe ─► rapport
                                                                                     │
                                          résumé LLM optionnel ─► verify_narrative ─┘ (rejeté si un chiffre n'est pas dans les preuves)
```

* **Outils** : seule source de chiffres. Chaque sortie est inscrite dans un `EvidenceLog` avec un identifiant : `ord:` (commande), `rev:` (avis), `kpi:` (table KPI), `mdl:` (sortie de modèle), `ctx:`.
* **Rapport** : cinq blocs fixes — faits, estimations, expériences d'autres clients, actions suggérées, limites. Chaque ligne porte ses identifiants de preuve.
* **LLM optionnel** (`--llm-url`, `--llm-model`, API compatible OpenAI, donc vLLM) : il choisit les outils (appel de fonctions) et rédige un résumé de 3 phrases. Ce résumé est **vérifié** : tout nombre absent des preuves, ou toute preuve inconnue, le fait rejeter ; le résumé déterministe est alors conservé. Sans LLM, tout fonctionne avec les mêmes outils.
* **Aucune fuite temporelle** : les commandes comparables et les taux de contexte n'utilisent que ce qui était connu avant l'achat de la commande cible. (Les tables KPI mensuelles ne sont pas utilisées pour BO1 : elles agrègent des issues observées après l'achat.)

## 2. Agent BO1 — DS1.3 « Anticiper les commandes problématiques »

Fichier : `src/agents/bo1_agent.py`. Entrée : un `order_id`, ou un mois (AAAA-MM) pour un tri.

| Outil | Rôle | Source |
|---|---|---|
| `get_order_context` | faits connus à l'approbation (région, catégorie, promesse, distance, valeur, port). L'issue réelle n'apparaît qu'avec `--audit` | `silver/orders_analysis` |
| `predict_risk` | scores DS1.1 (retard) et DS1.2 (note 1-2), percentile, tranche (élevé = top 10 %, modéré = 70e–90e, faible), **taux observé dans la tranche sur avr.–août 2018** | `model_{late,poor}.joblib` |
| `explain_risk` | facteurs : effet de chaque groupe de variables (promesse, géographie, vendeur, produit, panier, paiement, calendrier) sur le percentile, comparé à la commande médiane du TRAIN | occlusion sur le modèle |
| `find_similar_orders` | 8 commandes comparables (même État, promesse, distance, port, valeur, poids) dont l'issue était connue avant l'achat, avec extrait d'avis | features + avis |
| `get_context_rates` | taux de retard / note 1-2 de l'État, de la catégorie, du vendeur et de la marketplace sur les 90 jours avant l'achat, **uniquement avec les issues déjà connues à cette date** (date promise passée pour le retard, avis déjà publié pour la note) ; alerte si le vendeur a < 10 commandes à l'issue connue | silver/orders_analysis |
| `triage_orders` | classe les commandes d'un mois ; en mode audit, mesure rappel et précision du top 10 % | features |

**Choix de conception tenant compte de vos résultats (PR-AUC 0,107 / 0,22, signal faible)**

* L'agent ne donne **pas de probabilité** : la régression logistique à classes pondérées n'est pas calibrée (Brier test 0,27). Il donne un percentile et le **taux réellement observé** dans cette tranche sur la période TEST, avec l'effectif. C'est une calibration empirique par décile (`data/model/artifacts/model_card.json`).
* Le modèle par cible est celui choisi sur VALID dans `baseline_results.json` (règle reproductible sans regarder TEST). Option `--model gradient_boosting` dans `train_agent_models.py`.
* Les facteurs sont des **associations**. Olist n'enregistre aucune cause de retard : l'agent le dit et formule les actions comme des hypothèses à tester.
* Commande d'entraînement/validation : avertissement « score optimiste (dans l'échantillon) ». Commande multi-vendeurs : avertissement d'attribution.

Actions suggérées (règles liées aux facteurs dominants) : message proactif / promesse trop courte ; suivi renforcé de colis (région, distance) ; rappel au vendeur ; vérification du conditionnement ; contrôle de la fiche produit si seul le risque de mauvaise note est élevé ; sinon surveillance standard.

## 3. Agent BO2 — DS2.3 « Transformer les avis en actions »

Fichiers : `src/agents/bo2_agent.py`, `src/agents/bo2_nlp.py`. Entrée : mois, État, catégorie, ou question en français.

| Outil | Rôle |
|---|---|
| `kpi_context` | commandes, retards, avis 1-2, note moyenne du mois (gold) |
| `review_volume` | nombre d'avis écrits, part notée 1-2 **comparée à l'ensemble des avis** (biais de sélection), part traduite / « à vérifier » |
| `aspect_profile` | 9 aspects (livraison, qualité, article erroné/manquant, vendeur/service, emballage, conformité à l'annonce, prix, retour/remboursement, satisfaction) : critiques, éloges, **part des critiques venant de commandes en retard** |
| `emerging_complaints` | DS2.2 : part de critiques par aspect, mois cible vs **médiane des 12 mois précédents** + variabilité mensuelle (MAD), test unilatéral, correction de Benjamini-Hochberg ; termes nouveaux par log-odds avec a priori de Dirichlet (détecte ce que le lexique ne connaît pas) |
| `search_reviews` | avis représentatifs par TF-IDF sur portugais + traduction française, avec filtres mois / État / catégorie / sentiment / aspect |

* **Statut honnête de DS2.1** : c'est la baseline « mots-clés + note » du plan de modélisation. Évaluation **provisoire** sur 500 avis stratifiés annotés à l'aveugle par un LLM (accord LLM–humain κ ≈ 0,63 sur 40 avis ; 0,46 entre deux annotatrices) : F1 de détection moyen 0,67 (objectif 0,70), de 0,52 (articles erronés) à 0,83 (livraison) ; détail dans `quality/bo2_aspect_f1.json`. Chaque rapport le dit. L'interface `AspectModel` permet de brancher le transformeur multilingue sans modifier l'agent.
* `evaluate_agents.py` génère `quality/annotation_template.csv` (500 avis stratifiés par note) : annotez-le (−1 critique, 0 neutre, 1 positif, vide = non mentionné), renommez-le `annotated_reviews.csv`, relancez : l'évaluation calcule précision / rappel / F1 par aspect.
* Les extraits sont courts, portent leur `review_id`, et sont étiquetés « traduction automatique » ou « portugais original ».
* Chaque aspect critiqué est routé vers une équipe (logistique, catalogue, support vendeurs, service client…) ; si la majorité des critiques de livraison vient de commandes réellement en retard, l'agent renvoie vers BO1.

## 4. Évaluation (`src/evaluate_agents.py` → `quality/agent_evaluation.json`)

* **BO1** (60 commandes TEST stratifiées par tranche) : C1 structure complète ; C2 toutes les citations existent ; C3 pas de fuite de l'issue réelle ; C4 comparables connus avant l'achat ; C5 chiffres = recalcul indépendant et résumé vérifié ; C6 aucun langage causal. Utilité : rappel, précision et gain du top 10 % par mois, pour les deux cibles.
* **BO2** : backtest des alertes « livraison » contre un proxy indépendant (mois où le taux de retard dépasse 1,5 × la médiane des 3 mois précédents et 8 % ; sur vos données : nov. 2017, fév. et mars 2018) → précision et rappel d'alerte ; contrôles structurels sur 9 scénarios ; F1 par aspect dès que l'annotation existe.

## 4 bis. Résultats sur les vraies données Olist (vérification du 16/11/2026)

Exécution complète sur les données réelles (`train_agent_models.py` puis `evaluate_agents.py`), après trois corrections décrites plus bas.

**BO1 — contrôles sur 60 commandes TEST** : C1 à C6 réussis 60/60.

| Mois (TEST) | Retard : rappel top 10 % | Retard : gain vs hasard | Note 1-2 : rappel top 10 % | Note 1-2 : gain |
|---|---|---|---|---|
| 2018-04 | 40 % | ×4,0 | 22 % | ×2,2 |
| 2018-05 | 26 % | ×2,6 | 23 % | ×2,3 |
| 2018-06 | 34 % | ×3,4 | 23 % | ×2,3 |
| 2018-07 | 20 % | ×2,0 | 20 % | ×2,0 |
| 2018-08 | 11 % | ×1,1 | 24 % | ×2,4 |

Sur toute la période TEST : le top 10 % contient 24 % des retards (précision 10,7 % pour 4,4 % de base) et 23 % des notes 1-2. Le tri est utile pour prioriser, mais faiblit pour le retard en fin de période (août 2018 ≈ hasard).

**BO2 — alertes « livraison »** (janv. 2017 – août 2018) : 3 alertes, 3 vraies (nov. 2017, fév. 2018, mars 2018), aucune fausse, aucun mois manqué ; 9/9 scénarios structurels. F1 par aspect : toujours en attente de l'annotation.

**Corrections apportées lors de la vérification**

1. *Fuite temporelle dans `get_context_rates`* : les taux « des 3 mois précédents » venaient des tables KPI mensuelles, qui contiennent des retards et des avis observés **après** l'achat de la commande cible. Ils sont maintenant recalculés commande par commande avec les seules issues connues à la date d'achat.
2. *Détecteur BO2 aveugle après une crise* : avec une référence de 6 mois, le pic de novembre 2017 gonflait la variabilité (MAD) et février–mars 2018, les deux pires mois de retard, n'étaient pas signalés (rappel 1/3, une fausse alerte en décembre 2017). Avec 12 mois : 3/3, sans fausse alerte. Attention : ce réglage a été choisi en regardant ce même backtest ; il faudra le confirmer sur d'autres périodes.
3. *Contrôle C6* : les 4 échecs venaient de citations de clients (« parce que… »), pas de l'agent. Le contrôle ignore désormais le texte entre « ».
4. Compatibilité : `pandas>=2.2` au lieu de `>=3.0` (testé avec 2.2.3 et 3.0.5), conversion robuste des dates.

**Limite visible dans les rapports BO2** : la baseline par mots-clés + note classe parfois en « critique » un avis dont le texte est positif mais la note basse (ex. « Livraison dans les délais », 2/5). C'est attendu pour une baseline non évaluée ; l'annotation des 500 avis le mesurera.

## 5. Exécution

```bash
pip install -r requirements-agents.txt
python src/train_agent_models.py --project-dir .          # modèles BO1 (après build_model_features.py)
python src/run_agents.py bo1 --project-dir . --order <order_id>
python src/run_agents.py bo1 --project-dir . --triage 2018-06 --audit
python src/run_agents.py bo2 --project-dir . --month 2018-03
python src/run_agents.py bo2 --project-dir . --ask "Y a-t-il de nouvelles plaintes en juillet 2018 ?"
python src/evaluate_agents.py --project-dir .
python -m unittest tests/test_agents.py                    # SHOPINSIGHT_REPO=<dépôt> pour les tests synthétiques
# avec vLLM : ajouter --llm-url http://localhost:8000/v1 --llm-model <nom du modèle>
```

Pour un test honnête de BO1, prenez une commande de la période TEST (avr.–août 2018).

## 6. Limites assumées

Données historiques statiques ; signal de BO1 faible (le tri sert à prioriser une surveillance, pas à prédire un cas) ; BO2 repose sur un lexique non validé et sur des clients qui écrivent (plus mécontents) ; traductions automatiques ; aucune cause enregistrée. Les résultats de la section 4 bis ont été obtenus sur les vraies données Olist ; les tests unitaires (`tests/`) utilisent un jeu synthétique au même schéma.
