# ShopInsight

Projet REHEARSE (CRISP-DM) sur le jeu de données e-commerce brésilien Olist : préparation des données, traduction locale des avis en français, premiers modèles et deux agents (BO1 diagnostic préventif, BO2 voix du client).

## État d'avancement

| Phase CRISP-DM | Contenu | État |
|---|---|---|
| 1. Compréhension métier | 5 objectifs métier (BO), 15 objectifs data science (DSO) | fait |
| 2. Compréhension des données | exploration, qualité, relations entre variables | fait |
| 3. Préparation | nettoyage, valeurs manquantes, valeurs aberrantes, encodage, découpage chronologique, traduction des 42 687 avis | fait |
| 4. Modélisation | modèles de référence DS1.1 / DS1.2 ; agents DS1.3 (BO1) et DS2.3 (BO2) | en cours |
| 5–6. Évaluation, déploiement | annotation des avis (F1 par aspect), agents BO3–BO5, tableau de bord | à faire |

> **Données non incluses.** Le dossier `data/` (≈ 200 Mo) n'est pas versionné. Téléchargez l'archive Olist sur Kaggle
> ([Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce)),
> puis reconstruisez tout avec les commandes de la section « Exécution » ci-dessous.

## REHEARSE - Phase 2 : collecte, stockage et préparation des données

Cette phase prépare les données nécessaires aux cinq objectifs validés :

1. anticiper les commandes problématiques ;
2. analyser les avis clients ;
3. examiner les performances vendeurs ;
4. assister le client à partir de faits et d'expériences comparables ;
5. automatiser les KPI, les dashboards et le reporting.

## Types de données couverts

| Type | Données | Stockage |
|---|---|---|
| Structurées | commandes, clients, articles, paiements, produits, vendeurs, géolocalisation, notes | CSV source et tables CSV compressées |
| Semi-structurées | manifeste des sources, contrôles qualité, documents d'avis enrichis de métadonnées | JSON et JSONL compressé |
| Non structurées | titres et commentaires libres des avis clients, principalement en portugais | champ `text` dans `reviews_text.jsonl.gz` |

Le JSONL des avis est dérivé des fichiers Olist. Il ne constitue pas une nouvelle source et n'invente aucun commentaire.

## Organisation du stockage

```text
data/
  raw/       fichiers Olist originaux, non modifiés
  bronze/    inventaire, empreintes SHA-256 et profil des sources
  silver/    tables nettoyées et jointes pour l'analyse et les modèles
  gold/      KPI prêts pour dashboards et agent de reporting
  model/     variables des modèles (train / valid / test) et modèles des agents (artifacts/)
quality/     contrôles exécutés, rapport de qualité, résultats des modèles et des agents
docs/        dictionnaire des tables préparées, documentation des agents
src/         pipeline reproductible (prepare_data.py), validation (validate_outputs.py), traduction,
             variables et modèles de référence, agents (src/agents/)
tests/       tests unitaires des agents (jeu synthétique)
```

Le notebook `REHEARSE_Data_Preparation.ipynb` refait la préparation pas à pas, avec explications et graphiques.

## Jeux préparés principaux

- `orders_analysis.csv.gz` : une ligne par commande avec les résultats rétrospectifs et les indicateurs d'incohérence de dates. Utiliser pour l'analyse descriptive.
- `orders_model_base.csv.gz` : variables disponibles au moment de l'approbation et cibles séparées. Utiliser comme point de départ des modèles OM1 et OM4.
- `reviews_text.jsonl.gz` : tout le texte libre des avis (42 687 documents, dont 40 950 avec un message). Utiliser pour OM2 et la recherche d'avis de OM4.
- `multi_seller_order_links.csv.gz` : une ligne par commande multi-vendeurs et vendeur (2 622 lignes, 1 278 commandes). Utiliser pour étudier les plaintes de ces commandes à part, dans OM3.
- `seller_monthly_kpis.csv.gz` : indicateurs mensuels sur les commandes mono-vendeur. Utiliser pour OM3.
- `monthly_business_kpis.csv`, `state_monthly_kpis.csv.gz` et `category_monthly_kpis.csv.gz` : tables destinées à OM5.
- `geo_zip_centroid.csv.gz` : coordonnées par préfixe postal, calculées sur les points situés au Brésil.
- `metric_catalog.csv` : définition des KPI, formules, populations et objectifs associés.

## Règles de préparation essentielles

- Les articles et paiements sont agrégés avant leur jointure aux commandes ; les totaux restent égaux aux fichiers bruts.
- Un seul avis est sélectionné par commande pour les cibles : le dernier `review_answer_timestamp`, puis `review_id`. Tout le texte libre reste disponible pour le NLP, y compris les avis supplémentaires et les avis n'ayant qu'un titre.
- Un commentaire vide est une donnée manquante, pas un avis positif.
- Une livraison tardive signifie que le jour réel dépasse le jour promis. Les commandes sans date de livraison réelle restent sans étiquette de retard.
- La durée de livraison n'est calculée que pour les commandes au statut `delivered` avec date réelle (96 470).
- Les 775 commandes sans article portent la catégorie `no_items` ; `unknown` désigne uniquement des produits sans catégorie (1 393 commandes).
- `orders_model_base.csv.gz` exclut la livraison réelle, le statut final, les avis et les indicateurs d'incohérence de dates, tous postérieurs à l'approbation.
- Les KPI vendeurs excluent les commandes multi-vendeurs. Celles-ci sont analysées dans `multi_seller_order_links.csv.gz`, où le retard et l'avis restent des attributs de la commande, accompagnés de la part de chaque vendeur dans le montant.
- **Mois partiels** : toutes les tables KPI contiennent `is_complete_period` et `period_status`. Les mois 2016-09, 2016-12, 2018-09 et 2018-10 (moins de 100 commandes) et le mois sans commande 2016-11 sont marqués non complets. Les graphiques de tendance et l'agent de reporting doivent filtrer `is_complete_period == True`.
- **Incohérences de dates** : signalées, jamais corrigées ni supprimées. `flag_carrier_before_approval` (1 359), `flag_delivered_before_carrier` (23), `flag_delivered_status_missing_date` (8), `flag_delivery_date_on_undelivered_status` (6), et `flag_any_date_issue` (1 396 commandes au total).
- **Géolocalisation** : 261 831 points dupliqués retirés ; 33 points hors du Brésil exclus du calcul des centroïdes. 99 162 commandes disposent des coordonnées du client.
- Les évaluations futures devront utiliser un découpage chronologique.

## Exécution

À partir de l'archive Kaggle :

```powershell
python src/prepare_data.py `
  --source-zip chemin\vers\olist_original.zip `
  --project-dir chemin\vers\REHEARSE_Phase2_Data_Preparation
```

Ou à partir des CSV déjà extraits dans `data/raw` :

```powershell
python src/prepare_data.py --raw-dir data\raw --project-dir .
python src/validate_outputs.py --project-dir .
```

Le pipeline vérifie que les 9 fichiers bruts ont les empreintes SHA-256 de la version Olist d'origine.

Variables pour les modèles et modèles de référence (DS1.1 retard, DS1.2 note 1-2) :

```powershell
python src/build_model_features.py --project-dir .   # 61 variables, découpage chronologique
python src/train_baselines.py --project-dir .        # quality/baseline_results.json
```

- Uniquement des informations connues à l'approbation de la commande (plus la date de livraison promise, affichée à l'achat).
- Découpage chronologique : train oct. 2016 – déc. 2017, valid janv. – mars 2018, test avr. – août 2018.
- Résultats sur le test (PR-AUC) : retard 0,090 (régression logistique) à 0,107 (gradient boosting) pour un taux de base de 4,4 % ; note 1-2 0,223 pour un taux de base de 11,6 %. Signal réel mais faible.

## Traduction des avis en français

`src/translate_reviews.py` traduit localement les avis portugais vers le français. Aucun avis n'est envoyé à un service en ligne ; seuls les modèles sont téléchargés une fois (environ 600 Mo).

- Modèles : `Helsinki-NLP/opus-mt-ROMANCE-en` puis `Helsinki-NLP/opus-mt-en-fr` (pivot par l'anglais).
- Les 52 516 textes (messages et titres) ne comptent que 39 074 phrases uniques : chacune n'est traduite qu'une fois.
- **Traduction terminée** (novembre 2026, environ 4 h sur CPU) : 42 687 avis, dont 42 617 « traduit » et 70 « à vérifier » (0,2 %).
- Le cache `data/silver/translation_cache_fr.jsonl` permet de relancer le script après une interruption sans perdre le travail fait.
- Sortie : `data/silver/reviews_text_fr.jsonl.gz`, avec pour chaque avis `text_original_pt`, `text_fr`, `title_original_pt`, `title_fr`, `translation_status` (`traduit` / `vide` / `à vérifier`) et `translation_flags`. Le fichier `reviews_text.jsonl.gz` n'est pas modifié.
- Contrôle : `quality/translation_report.json`, et `quality/translation_sample_for_review.csv` contenant 200 avis tirés au hasard à vérifier à la main (colonne « correct »).
- Une traduction est marquée `à vérifier` si elle est vide, identique au portugais, de longueur anormale ou répétitive.

```powershell
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-translation.txt
python src/translate_reviews.py --project-dir . --limit 200   # test rapide
python src/translate_reviews.py --project-dir .               # traduction complète
```

## Agents BO1 et BO2

Deux agents réalisent les DSO agentiques DS1.3 et DS2.3. Chaque rapport sépare les **faits observés**, les **estimations du modèle** et les **expériences d'autres clients**, et chaque ligne cite ses preuves (`ord:`, `rev:`, `kpi:`, `mdl:`). Un LLM (serveur compatible OpenAI, par ex. vLLM) est optionnel ; sans lui, tout fonctionne.

- **BO1 — diagnostic préventif** (`src/agents/bo1_agent.py`) : pour une commande, risque de retard et de note 1-2 (percentile et taux réellement observé dans la tranche, pas de probabilité brute), facteurs associés, 8 commandes comparables terminées avant l'achat, taux récents de la région, de la catégorie et du vendeur calculés uniquement avec les issues connues à la date d'achat, actions suggérées. Peut aussi classer les commandes d'un mois.
- **BO2 — voix du client** (`src/agents/bo2_agent.py`, `bo2_nlp.py`) : pour un mois, un État, une catégorie ou une question en français, aspects critiqués et appréciés (9 aspects), plaintes émergentes (référence : médiane des 12 mois précédents, correction de Benjamini-Hochberg), termes nouveaux, avis représentatifs traduits, équipe à mobiliser.

```powershell
pip install -r requirements-agents.txt
python src/train_agent_models.py --project-dir .        # après build_model_features.py
python src/run_agents.py bo1 --project-dir . --order <order_id>
python src/run_agents.py bo1 --project-dir . --triage 2018-06
python src/run_agents.py bo2 --project-dir . --month 2018-03
python src/run_agents.py bo2 --project-dir . --ask "Y a-t-il de nouvelles plaintes en juillet 2018 ?"
python src/evaluate_agents.py --project-dir .           # quality/agent_evaluation.json
python -m unittest tests/test_agents.py
```

**Résultats sur les vraies données Olist** (`quality/agent_evaluation.json`) :

- BO1 : 6 contrôles (structure, citations, pas de fuite, comparables passés, chiffres exacts, pas de langage causal) réussis sur 60 commandes test sur 60. Sur avril – août 2018, le top 10 % des scores contient 24 % des retards et 23 % des notes 1-2 (10 % attendus au hasard) ; le gain pour le retard baisse en fin de période (août 2018 ≈ hasard).
- BO2 : alertes « livraison » de janv. 2017 à août 2018 : 3 alertes, 3 justes (nov. 2017, fév. 2018, mars 2018), aucun mois manqué ; 9 scénarios structurels sur 9.
- L'analyse par aspect (mots-clés + note) n'est pas encore évaluée : annoter `quality/annotation_template.csv`, le renommer `annotated_reviews.csv` et relancer `evaluate_agents.py` pour obtenir le F1 par aspect.

Détails, choix de conception et limites : `docs/agents_BO1_BO2.md`.

## Historique des versions

**V3 (novembre 2026)** : modélisation et agents.

- Traduction française complète des 42 687 avis.
- 61 variables pour les modèles, découpage chronologique, modèles de référence DS1.1 et DS1.2.
- Notebook de préparation exécuté pas à pas.
- Agents BO1 (DS1.3) et BO2 (DS2.3), évalués sur les vraies données.

**V2 (octobre 2026)** : application des étapes de nettoyage prévues dans la présentation et non encore réalisées.

- Nouvelle table `multi_seller_order_links.csv.gz` pour traiter à part les commandes multi-vendeurs.
- Étiquette `no_items` distincte de `unknown`.
- Durée de livraison limitée aux commandes livrées (96 476 → 96 470, cohérent avec la présentation).
- Mois partiels et mois manquant 2016-11 marqués dans toutes les tables KPI.
- Indicateurs d'incohérence de dates.
- Centroïdes géographiques sans points hors du Brésil ; coordonnées client ajoutées.
- Avis n'ayant qu'un titre ajoutés au JSONL (40 950 → 42 687 documents ; `has_message` permet de retrouver les 40 950).
- Contrôles qualité étendus de 7 à 37, et script de validation indépendante.

## Limites

Olist est historique et statique. Le reporting mensuel peut être démontré en révélant progressivement les mois d'achat, mais il ne s'agit pas d'un flux temps réel. Les commentaires sont en portugais ; leur traduction française est automatique : l'échantillon de 200 avis doit être relu, et dans environ 6,6 % des commentaires sur plusieurs lignes une phrase peut manquer. Les thèmes et sentiments nécessitent un échantillon annoté pour une évaluation valide. Le signal des modèles BO1 est faible : il sert à prioriser une surveillance, pas à prédire un cas individuel. Aucune cause de retard n'est enregistrée dans Olist : les facteurs donnés par les agents sont des associations. Le classeur `REHEARSE_Phase2_Summary.xlsx` provient de la V1 : ses chiffres principaux restent valables, mais il n'intègre pas les nouveaux indicateurs.

Source : Brazilian E-Commerce Public Dataset by Olist, Kaggle. Licence affichée par la source : CC BY-NC-SA 4.0.


## Rapport de validation technique (novembre 2026)

Le rapport **[docs/ShopInsight_Dossier_Technique.pdf](docs/ShopInsight_Dossier_Technique.pdf)** (12 pages) présente l'état du projet pour validation : réalisation étape par étape, pile technique, architecture, workflows, coordination des agents BO1, BO2 et BO3, évaluation chiffrée de chaque agent et de la couche d'IA, limites et reproduction. Les fiches détaillées des DSO de BO3 sont ci-dessous.

## BO3 : audit des vendeurs (DS3.1, DS3.2, DS3.3)

L'objectif métier est de **prioriser l'investigation des vendeurs dont la performance est inhabituelle ou se dégrade**. Pour cela, on les compare à une référence pertinente et à leur propre passé. Les trois DSO s'enchaînent :

- DS3.1 fournit la **référence** : à qui comparer.
- DS3.2 décide des **alertes** : qui se dégrade.
- DS3.3 **explique** dans un audit sourcé : pourquoi, et que faire.

### Socle commun

- **Indicateurs** (commandes mono-vendeur uniquement) :
  - `late` : livraison après la date annoncée ;
  - `poor` : avis de 1 ou 2 étoiles ;
  - `handover` : remise au transporteur après la date limite d'expédition.
- **Règle « à date »** : on décide à la date T, au début du mois suivant le mois analysé. Une issue n'entre dans un calcul que si elle était connue à T.
- **Fenêtres** (dates d'achat) :
  - récente : [T − 90 j, T) ;
  - historique : [T − 365 j, T − 90 j) ;
  - future : [T, T + 60 j), qui sert **uniquement à l'évaluation**.
- **Découpage chronologique** :
  - TRAIN : décisions de 2017-03 à 2017-12 ;
  - validation : trois plis glissants (2017-T3, 2017-T4, 2018-T1) ;
  - TEST : décisions de 2018-04 à 2018-06, lu une seule fois selon un protocole écrit à l'avance.
- **Vérité prospective** : un vendeur est considéré dégradé si, sur les 60 jours suivants, son taux est significativement supérieur à la référence ou à son historique (binomial unilatéral, p < 0,05, au moins 5 commandes).
- **Pipeline** :

| Étape | Commande | Produit | Durée |
|---|---|---|---|
| Panel « à date » | `python src/build_seller_panel.py --project-dir .` | `data/model/seller_panel_asof` (48 876 lignes, 1 762 vendeurs) | ≈ 45 s |
| DS3.1 + DS3.2 | `python src/train_seller_models.py --project-dir .` | `quality/bo3_model_results.json`, historique des alertes, historique mensuel | ≈ 3,3 min |
| DS3.3 | `python src/evaluate_bo3.py --project-dir .` | `quality/bo3_agent_evaluation.json` (C1–C7) | ≈ 2 min |

Le code partagé est dans [src/agents/bo3_sellers.py](src/agents/bo3_sellers.py) : données « à date », Wilson, Benjamini-Hochberg, détecteurs, groupes de pairs et concurrents directs. Les outils de l'agent sont dans [src/agents/bo3_agent.py](src/agents/bo3_agent.py).

### DS3.1 : vendeurs comparables et positionnement

| Rubrique | Contenu |
|---|---|
| Construction | Profil du vendeur à T, calculé sur 12 mois **sans aucune issue** : parts de catégories, destinations, volume, prix médian, part du port, poids, délai annoncé. Les variables sont standardisées. |
| Modèles comparés | Marketplace entière, même catégorie, k plus proches voisins (k = 10/20/40), KMeans (5/8/12 groupes), segments volume × région. |
| Métrique | **Perte logarithmique par commande** du taux des pairs pour prédire le taux du vendeur sur les 60 jours suivants, relative à la marketplace (= 1,000). C'est une règle de score propre, adaptée à la question « cette référence prédit-elle le futur ? ». La stabilité mensuelle est mesurée par l'ARI et le Jaccard. |
| Benchmark | Même catégorie : 1,008 (TEST). KMeans : 1,001 à 1,002. Voisins : 1,002 à 1,019. Segments : 1,0003 à 1,0041. |
| Résultat | Aucun regroupement ne prédit mieux que la marketplace, qui devient donc **la référence des alertes**. Les groupes restent descriptifs : rang dans la catégorie et parmi les **20 concurrents directs**, médiane, seuil du meilleur quart (cible du plan d'action). |
| Carte du marché | KMeans à 5 familles sur 5 dimensions métier (prix, délai, volume, part du port, clients locaux), projection ACP à axes nommés. La séparation est 2,6 fois meilleure qu'avec le profil complet (silhouette 0,179 contre 0,068). Chaque famille a son évolution mensuelle. |
| Sur la plateforme | **Fiche vendeur › onglet « Concurrence & classement »** : rangs, graphique vendeur / médianes / meilleur quart, profil commercial, concurrents directs. **Page « Carte du marché »**. La référence « marketplace X % » figure sur les cartes de la fiche. |
| API | `/api/bo3/sellers/{id}/peers`, `/benchmark`, `/comparison`, `/api/bo3/market-map`, `/market-map/trends`, `/marketplace` |

### DS3.2 : détection de dégradation

| Rubrique | Contenu |
|---|---|
| Construction | Pour chaque vendeur × mois × indicateur, on calcule le taux récent (90 j, issues connues à T), la référence marketplace et l'historique du vendeur rétréci vers la référence. On évalue 12 détecteurs, avec correction de Benjamini-Hochberg. |
| Réglage | Sur les plis uniquement. Un réglage est admissible s'il alerte au plus 10 % des cas éligibles dans **chaque** pli, ce qui correspond à la capacité d'investigation. On retient ensuite le meilleur F1 moyen. |
| Métriques | **Précision** (coût d'une investigation inutile), **rappel**, **F1**, **alertes par mois** (charge de travail) et **gain** = précision / taux de base. Le gain est indispensable parce que l'événement est rare (≈ 3 %). |
| Niveau retenu | Détecteur bêta-binomial (a priori = référence, τ = 0,99, ≥ 30 issues). Sur TEST : précision **20,5 %**, rappel 31,1 %, F1 0,247, 45 alertes/mois, **gain ×6,1** (taux de base 3,3 %). |
| Tendance retenue | Binomial + BH contre l'historique (α = 0,05, ≥ 30 issues). Sur TEST : précision 7,8 %, rappel 14,1 %, gain ×2,4. C'est un signal faible, présenté comme tel. |
| Benchmark | 12 détecteurs. Niveau : règle « > facteur × référence », binomial + BH, bêta-binomial, observé/attendu. Tendance : règle, binomial + BH (historique court et long), CUSUM ×1,5/×2/×3, bayésien, EWMA. Le tableau complet est en section 8.5 du rapport. |
| Sévérité | Règle fixée à l'avance. Précision sur TEST : élevée 28,2 %, moyenne 21,8 %, faible 0 %. L'ordre est respecté, donc la sévérité sert à prioriser. La règle de persistance n'a pas été adoptée. |
| Dégradations simulées | Taux de détection en 3 mois pour une hausse de +5 / +10 / +20 points : retard 20 / 32 / 52 %, avis 8 / 12 / 32 %, remise 4 / 16 / 48 %. |
| Historique | Rejoué de 2017-03 à 2018-08 : 1 426 lignes (526 nouvelles, 407 en cours, 493 résolues). |
| Extensions | Retards par État de destination (≥ 15 livraisons, BH q < 0,05, ≥ 1,5 × la référence), non évalué rétrospectivement. Liste « À appeler cette semaine », avec motif, e-mail et script. |
| Sur la plateforme | **Page « Alertes vendeurs »** : alertes du mois expliquées en clair et réparties par priorité, historique, retards par État. **Page « À appeler cette semaine »**. Badges de l'annuaire. Sur la fiche vendeur : bandeau d'état, badges des cartes, courbe « Trajectoire sur 18 mois ». |
| API | `/api/bo3/alerts`, `/alert-history`, `/state-alerts`, `/call-list`, `/sellers/{id}/deterioration`, `/strengths`, `/history` |

### DS3.3 : agent d'audit `SellerAuditAgent`

| Rubrique | Contenu |
|---|---|
| Architecture | Outils Python déterministes → EvidenceLog (identifiants citables `sel:`, `peer:`, `kpi:`, `alr:`, `ord:`, `rev:`, `mdl:`) → rapport (faits, estimations, comparaisons, actions, limites) → résumé vérifié par `verify_bo3_narrative` → couche IA facultative, dont chaque élément est revalidé contre les preuves. Le cadre `src/agents/core.py` (partagé avec BO1/BO2) n'est pas modifié. |
| Outils | `get_seller_profile`, `get_peer_group`, `competitive_benchmark`, `compare_to_peers`, `detect_deterioration`, `list_alerts`, `find_strengths`, `get_seller_history`, `get_seller_orders`, `seller_voice`, `get_seller_geography`, `seller_state_alerts`, `multi_seller_exposure`, `market_map`, `market_family_trends`, `call_list`, `marketplace_brief` |
| Modèles | Pas de modèle entraîné propre : l'agent appelle DS3.1 et DS3.2. S'y ajoutent la traduction locale MarianMT (portugais → français, à la demande) et des modèles de langage gratuits via OpenRouter, qui servent uniquement à la rédaction : Nemotron 3.5 Super principal, plus 5 modèles de repli. |
| Métriques | Contrôles C1–C7 sur 60 audits TEST stratifiés : structure, citations, absence d'information future (mêmes résultats sur des données amputées après T), pairs passés, chiffres exacts, pas de causalité, effectifs affichés. |
| Résultats | **C1–C7 : 60/60** pour chaque contrôle. Couche IA sur un audit réel : 34 éléments sur 34 validés après une passe de correction. |
| Benchmark IA | 8 cas par modèle. Ernie 5.5 Flash : JSON conforme 100 %, éléments validés 93,7 %, juge 4,5/5, latence 28 s. Nemotron 3.5 Super : JSON 87,5 %, éléments validés 88,5 %, juge 4,53/5, latence 19 s. Coût : 0 $. La sélection n'est pas conclue (quota gratuit). |
| Sur la plateforme | **Fiche vendeur** : bandeau d'état, 3 cartes (taux sur 90 jours comparé à la marketplace, sources cliquables) et 4 onglets (Bilan & plan d'action par l'IA validée, Concurrence & classement, Clients/catalogue/historique, Voix du client & commandes). **Bouton « Télécharger le Bilan PDF »**. **Assistant flottant** sur toutes les pages ; il répond directement à partir des données si le quota IA est épuisé. |
| API | `/api/bo3/sellers/{id}/audit`, `/api/bo3/ask`, `/api/llm/sellers/{id}/analysis`, `/api/llm/sellers/{id}/chat`, `/api/llm/chat`, `/api/reports/sellers/{id}.pdf`, `/api/reports/sellers/{id}/evidence.csv` |

**Lisibilité.** Chaque information n'apparaît qu'à un seul endroit de l'interface. Chaque pourcentage est donné avec sa base (« sur N commandes ») et sa référence. Les États brésiliens sont écrits en toutes lettres (São Paulo, Minas Gerais…) partout, y compris dans les rapports BO1/BO2 affichés, le PDF et les réponses de l'IA.

## Démarrage rapide

Après la préparation des données ci-dessus :

```powershell
pip install -r requirements.txt -r requirements-agents.txt -r requirements-api.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu ; pip install -r requirements-translation.txt   # avis traduits en français
python src/build_model_features.py --project-dir . ; python src/train_agent_models.py --project-dir .
python src/build_seller_panel.py --project-dir .   ; python src/train_seller_models.py --project-dir .
python -m uvicorn backend.app.main:app --port 8000         # API : http://localhost:8000/docs
cd frontend ; npm install ; npm run dev                     # interface : http://localhost:5173
```

Tests : `python -m unittest tests/test_bo3.py tests/api/test_api.py tests/api/test_llm.py tests/test_agents.py -v` (72 tests) ; `cd frontend ; npm run build ; node e2e/smoke.mjs` (16 contrôles).

La couche IA est facultative. Pour l'activer, copier `.env.example` en `.env` et renseigner `OPENROUTER_API_KEY` (modèles gratuits uniquement, budget 0 $).
Documentation d'origine conservée : [docs/data_dictionary.md](docs/data_dictionary.md), [docs/agents_BO1_BO2.md](docs/agents_BO1_BO2.md).

## BO4 : assistant client historique

BO4 ajoute des intervalles de livraison P10/P50/P90 conformalisés, une recherche hybride d'expériences (TF-IDF, BM25, BGE-M3, FAISS, RRF) et un assistant dont chaque affirmation renvoie à une preuve. Toutes les fonctions acceptent `as_of` et masquent jalons, issues et avis futurs. La page **BO4 — Assistant client** et l'API `/api/bo4` sont intégrées à la plateforme.

Le protocole CRISP-DM, l'architecture, l'audit de fuite et les commandes sont dans [docs/agents_BO4.md](docs/agents_BO4.md). Les artefacts volumineux restent hors Git, mais les rapports `quality/bo4_*` consignent désormais une exécution complète sur les données Olist originales. Gradient Boosting est sélectionné (test : MAE 3,846 jours, RMSE 5,923, PICP 0,762, MPIW 11,908 et Winkler 18,576). Les métriques de pertinence retrieval restent volontairement vides tant que les 1 464 candidats n'ont pas reçu de jugements humains.

```powershell
pip install -r requirements.txt -r requirements-agents.txt -r requirements-api.txt -r requirements-bo4.txt
python src/train_bo4_models.py --project-dir .
python src/build_bo4_index.py --project-dir .
python src/evaluate_bo4.py --project-dir .
python src/evaluate_bo4_agent.py --project-dir . --scenarios 60
python src/run_agents.py bo4 --order <order_id> --as-of 2018-06-01 --ask "Quand arrivera ma commande ?"
```
